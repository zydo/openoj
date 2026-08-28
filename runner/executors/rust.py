import re
import textwrap
from pathlib import Path
from typing import Any

from .base import PreparedProgram
from .compiled import CompiledExecutor
from .typed import (
    encode_case,
    function_signature,
    provided_node_class,
    rust_parameter_type,
    rust_type,
    struct_item_spec,
    uses_struct_kinds,
)


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _read_expression(spec: dict[str, Any], reader: str = "openoj_reader") -> str:
    kind = spec["kind"]
    if kind == "integer":
        return f"{reader}.i32()?" if spec.get("bits", 32) == 32 else f"{reader}.i64()?"
    if kind == "number":
        return f"{reader}.number()?"
    if kind == "boolean":
        return f"{reader}.boolean()?"
    if kind == "string":
        return f"{reader}.text()?"
    if kind == "linked_list":
        return f"{reader}.linked_list()?"
    if kind == "binary_tree":
        return f"{reader}.binary_tree()?"
    if kind == "nary_tree":
        return f"{reader}.nary_tree()?"
    if kind == "quad_tree":
        return f"{reader}.quad_tree()?"
    if kind == "nested":
        return f"{reader}.nested()?"
    if kind == "next_tree":
        return f"{reader}.next_tree()?"
    if kind == "circular_list":
        return f"{reader}.circular_list()?"
    if kind == "doubly_circular":
        return f"{reader}.doubly_circular()?"
    if kind == "multi_list":
        return f"{reader}.multi_list()?"
    if kind == "graph":
        return f"{reader}.graph()?"
    if kind == "random_list":
        return f"{reader}.random_list()?"
    if kind == "struct":
        return f"{reader}.read{_snake_case(spec['class'])}()?"
    nested = _read_expression(spec["items"], "reader")
    return f"{reader}.array(|reader| Ok({nested}))?"


class RustExecutor(CompiledExecutor):
    language = "rust"
    address_space_overhead_mb = 0
    # rustc's parallel codegen spawns one worker thread per CPU; each thread
    # counts against RLIMIT_NPROC, so larger submissions ICE with "failed to
    # spawn work thread" unless the cap sits well above the thread count.
    # This bounds the trusted compiler only — user code still runs under the
    # 16-process runtime sandbox.
    max_processes = 48
    compiler_memory_mb = 2048
    # rustc's first link on a cold page cache easily exceeds the shared
    # 10-second budget; the worker pre-warms the toolchain at startup so this
    # only covers genuinely large submissions.
    compiler_timeout_seconds = 25
    compiler_path = "/usr/bin/rustc"
    benchmark_command = ("/runner/benchmarks/rust",)
    reference_benchmark_ms = 18.0

    def prepare(
        self,
        job_root: Path,
        scratch: Path,
        code: str,
        invocation: dict[str, Any],
        limits: dict[str, Any],
        assembly: dict[str, dict[str, str]] | None = None,
    ) -> PreparedProgram:
        if invocation.get("type") == "design":
            from .rust_design import prepare_design
            return prepare_design(self, job_root, scratch, code, invocation, assembly)
        if invocation.get("type") == "interactive":
            from .rust_interactive import prepare_interactive
            return prepare_interactive(self, job_root, scratch, code, invocation, assembly)
        parameters, return_type, method = function_signature(invocation, self.language)
        # The assembled program: common-library and problem-provided source
        # is prepended as one crate's leading items (types the submission
        # then uses directly).
        assembly_source = "".join(
            content + "\n"
            for part in ("common", "provided")
            for name, content in sorted((assembly or {}).get(part, {}).items())
            if name.endswith(".rs")
        )
        structs = uses_struct_kinds(invocation)
        item_read = _read_expression(struct_item_spec(invocation), "self")
        graph_class = provided_node_class(invocation, "graph")
        random_class = provided_node_class(invocation, "random_list")
        struct_codecs = ""
        result_expression = "openoj_actual.openoj_json()"
        if "list" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn linked_list(&mut self) -> Result<Option<Box<ListNode>>, String> {{
                        if self.take(1)?[0] == 0 {{ return Ok(None); }}
                        let length = self.u32()? as usize;
                        let mut nodes: Vec<ListNode> = Vec::with_capacity(length);
                        for _ in 0..length {{ nodes.push(ListNode {{ val: {item_read}, next: None }}); }}
                        let mut head: Option<Box<ListNode>> = None;
                        for node in nodes.into_iter().rev() {{
                            head = Some(Box::new(ListNode {{ val: node.val, next: head }}));
                        }}
                        Ok(head)
                    }}
                }}
                fn openoj_list_node_json(head: &Option<Box<ListNode>>) -> String {{
                    let mut output = String::from("[");
                    let mut current = head.as_deref();
                    let mut first = true;
                    while let Some(node) = current {{
                        if !first {{ output.push(','); }}
                        first = false;
                        let _ = write!(output, "{{}}", node.val);
                        current = node.next.as_deref();
                    }}
                    output.push(']');
                    output
                }}
                """
            )
            if return_type.get("kind") == "linked_list":
                result_expression = "Ok(openoj_list_node_json(&openoj_actual))"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "linked_list":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|part| openoj_list_node_json(part))"
                    ".collect::<Vec<String>>().join(\",\")))"
                )
        if "tree" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn binary_tree(&mut self) -> Result<Option<Box<TreeNode>>, String> {{
                        let length = self.u32()? as usize;
                        let mut pool: Vec<Option<Box<TreeNode>>> = Vec::with_capacity(length);
                        for _ in 0..length {{
                            if self.take(1)?[0] == 1 {{
                                pool.push(Some(Box::new(TreeNode {{ val: {item_read}, left: None, right: None }})));
                            }} else {{
                                pool.push(None);
                            }}
                        }}
                        if pool.is_empty() || pool[0].is_none() {{ return Ok(None); }}
                        let mut root = pool[0].take();
                        let mut queue: std::collections::VecDeque<*mut TreeNode> = std::collections::VecDeque::new();
                        queue.push_back(root.as_mut().unwrap().as_mut());
                        let mut index = 1usize;
                        while let Some(node_pointer) = queue.pop_front() {{
                            for side in 0..2 {{
                                if index >= pool.len() {{ break; }}
                                if pool[index].is_some() {{
                                    let mut child = pool[index].take().unwrap();
                                    queue.push_back(child.as_mut() as *mut TreeNode);
                                    unsafe {{
                                        if side == 0 {{ (*node_pointer).left = Some(child); }}
                                        else {{ (*node_pointer).right = Some(child); }}
                                    }}
                                }}
                                index += 1;
                            }}
                        }}
                        Ok(root)
                    }}
                }}
                fn openoj_tree_node_json(root: &Option<Box<TreeNode>>) -> String {{
                    let mut items: Vec<String> = Vec::new();
                    let mut queue: std::collections::VecDeque<Option<&TreeNode>> = std::collections::VecDeque::new();
                    if root.is_some() {{ queue.push_back(root.as_deref()); }}
                    while let Some(entry) = queue.pop_front() {{
                        match entry {{
                            None => items.push("null".to_string()),
                            Some(node) => {{
                                items.push(node.val.to_string());
                                queue.push_back(node.left.as_deref());
                                queue.push_back(node.right.as_deref());
                            }}
                        }}
                    }}
                    while items.last().map_or(false, |value| value == "null") {{ items.pop(); }}
                    format!("[{{}}]", items.join(","))
                }}
                """
            )
            if return_type.get("kind") == "binary_tree":
                result_expression = "Ok(openoj_tree_node_json(&openoj_actual))"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "binary_tree":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|tree| openoj_tree_node_json(tree))"
                    ".collect::<Vec<String>>().join(\",\")))"
                )
        if "nary_tree" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn nary_tree(&mut self) -> Result<Option<Box<Node>>, String> {{
                        let length = self.u32()? as usize;
                        let mut pool: Vec<Option<Box<Node>>> = Vec::with_capacity(length);
                        for _ in 0..length {{
                            if self.take(1)?[0] == 1 {{
                                pool.push(Some(Box::new(Node {{ val: {item_read}, children: Vec::new() }})));
                            }} else {{
                                pool.push(None);
                            }}
                        }}
                        if pool.is_empty() || pool[0].is_none() {{ return Ok(None); }}
                        let mut root = pool[0].take();
                        let mut queue: std::collections::VecDeque<*mut Node> = std::collections::VecDeque::new();
                        queue.push_back(root.as_mut().unwrap().as_mut());
                        // Display wire: slot 1 closes the root group, then
                        // every node's children run until that node's own
                        // separator slot; tolerate the marker's absence.
                        let mut index = if length > 1 && pool[1].is_some() {{ 1 }} else {{ 2 }};
                        while let Some(node_pointer) = queue.pop_front() {{
                            while index < pool.len() {{
                                let slot = pool[index].take();
                                index += 1;
                                match slot {{
                                    Some(mut child) => {{
                                        queue.push_back(child.as_mut() as *mut Node);
                                        unsafe {{ (*node_pointer).children.push(Some(child)); }}
                                    }}
                                    None => break,
                                }}
                            }}
                        }}
                        Ok(root)
                    }}
                }}
                fn openoj_nary_json(root: &Option<Box<Node>>) -> String {{
                    // Display wire: root value, the marker closing the root
                    // group, then each node's children followed by its own
                    // marker; trailing markers are trimmed.
                    let mut items: Vec<String> = Vec::new();
                    if let Some(node) = root {{
                        items.push(node.val.to_string());
                        items.push("null".to_string());
                        let mut queue: std::collections::VecDeque<&Node> = std::collections::VecDeque::new();
                        queue.push_back(node);
                        while let Some(current) = queue.pop_front() {{
                            for child in current.children.iter().flatten() {{
                                items.push(child.val.to_string());
                                queue.push_back(child);
                            }}
                            items.push("null".to_string());
                        }}
                    }}
                    while items.last().map_or(false, |value| value == "null") {{ items.pop(); }}
                    format!("[{{}}]", items.join(","))
                }}
                """
            )
            if return_type.get("kind") == "nary_tree":
                result_expression = "Ok(openoj_nary_json(&openoj_actual))"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "nary_tree":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|tree| openoj_nary_json(tree))"
                    ".collect::<Vec<String>>().join(\",\")))"
                )
        if "quad_tree" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn quad_tree(&mut self) -> Result<Option<Box<QuadNode>>, String> {{
                        if self.take(1)?[0] == 0 {{ return Ok(None); }}
                        let is_leaf = self.take(1)?[0] == 1;
                        let val = self.take(1)?[0] == 1;
                        let mut node = Box::new(QuadNode {{ val, is_leaf, top_left: None, top_right: None, bottom_left: None, bottom_right: None }});
                        if !is_leaf {{
                            node.top_left = self.quad_tree()?;
                            node.top_right = self.quad_tree()?;
                            node.bottom_left = self.quad_tree()?;
                            node.bottom_right = self.quad_tree()?;
                        }}
                        Ok(Some(node))
                    }}
                }}
                fn openoj_quad_json(node: &Option<Box<QuadNode>>) -> String {{
                    // LC display wire: one flat preorder list of [isLeaf,
                    // val] pairs; a non-leaf's val normalizes to 0.
                    if node.is_none() {{ return "null".to_string(); }}
                    fn append(node: &Option<Box<QuadNode>>, output: &mut String) {{
                        let Some(inner) = node else {{ output.push_str("null"); return; }};
                        if inner.is_leaf {{
                            output.push_str(&format!("[1,{{}}]", if inner.val {{ 1 }} else {{ 0 }}));
                            return;
                        }}
                        output.push_str("[0,0]");
                        for side in [&inner.top_left, &inner.top_right, &inner.bottom_left, &inner.bottom_right] {{
                            output.push(',');
                            append(side, output);
                        }}
                    }}
                    let mut output = String::from("[");
                    append(node, &mut output);
                    output.push(']');
                    output
                }}
                """
            )
            if return_type.get("kind") == "quad_tree":
                result_expression = "Ok(openoj_quad_json(&openoj_actual))"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "quad_tree":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|tree| openoj_quad_json(tree))"
                    ".collect::<Vec<String>>().join(\",\")))"
                )
        if "nested" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn nested(&mut self) -> Result<NestedInteger, String> {{
                        let tag = self.take(1)?[0];
                        if tag == 1 {{ return Ok(NestedInteger::with_integer(self.i32()?)); }}
                        if tag != 2 {{ return Err("Invalid nested tag".into()); }}
                        let length = self.u32()? as usize;
                        let mut value = NestedInteger::new();
                        for _ in 0..length {{ value.add(self.nested()?); }}
                        Ok(value)
                    }}
                }}
                fn openoj_nested_json(value: &NestedInteger) -> Result<String, String> {{
                    if value.is_integer() {{ return Ok(value.get_integer().to_string()); }}
                    let items: Result<Vec<String>, String> = value.get_list().iter().map(openoj_nested_json).collect();
                    Ok(format!("[{{}}]", items?.join(",")))
                }}
                """
            )
            if return_type.get("kind") == "nested":
                result_expression = "Ok(openoj_nested_json(&openoj_actual)?)"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "nested":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(openoj_nested_json)"
                    ".collect::<Result<Vec<String>, String>>()?.join(\",\")))"
                )
        if "next_tree" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn next_tree(&mut self) -> Result<Option<std::rc::Rc<std::cell::RefCell<NodeWithNext>>>, String> {{
                        let length = self.u32()? as usize;
                        let mut slots: Vec<Option<std::rc::Rc<std::cell::RefCell<NodeWithNext>>>> = Vec::with_capacity(length);
                        for _ in 0..length {{
                            if self.take(1)?[0] == 1 {{
                                slots.push(Some(std::rc::Rc::new(std::cell::RefCell::new(NodeWithNext {{ val: {item_read}, left: None, right: None, next: None, parent: None }}))));
                            }} else {{
                                slots.push(None);
                            }}
                        }}
                        if slots.is_empty() || slots[0].is_none() {{ return Ok(None); }}
                        let root = slots[0].clone().unwrap();
                        let mut queue: std::collections::VecDeque<std::rc::Rc<std::cell::RefCell<NodeWithNext>>> = std::collections::VecDeque::new();
                        queue.push_back(root.clone());
                        let mut index = 1usize;
                        while let Some(node) = queue.pop_front() {{
                            for side in 0..2 {{
                                if index >= slots.len() {{ break; }}
                                let slot = slots[index].clone();
                                index += 1;
                                if let Some(child) = slot {{
                                    child.borrow_mut().parent = Some(node.clone());
                                    if side == 0 {{ node.borrow_mut().left = Some(child.clone()); }}
                                    else {{ node.borrow_mut().right = Some(child.clone()); }}
                                    queue.push_back(child);
                                }}
                            }}
                        }}
                        Ok(Some(root))
                    }}
                }}
                fn openoj_next_tree_json(root: &Option<std::rc::Rc<std::cell::RefCell<NodeWithNext>>>) -> String {{
                    // LC display wire: values with one null marker between
                    // adjacent levels; the walk advances to the first child
                    // found anywhere in the level (left, else right) so
                    // imperfect trees serialize too.
                    let mut items: Vec<String> = Vec::new();
                    let mut level = root.clone();
                    while let Some(node) = level {{
                        let mut next_level: Option<std::rc::Rc<std::cell::RefCell<NodeWithNext>>> = None;
                        let mut cursor = Some(node);
                        while let Some(current) = cursor {{
                            let (value, next, left, right) = {{
                                let borrowed = current.borrow();
                                (borrowed.val, borrowed.next.clone(), borrowed.left.clone(), borrowed.right.clone())
                            }};
                            items.push(value.to_string());
                            if next_level.is_none() {{
                                if left.is_some() {{ next_level = left; }}
                                else if right.is_some() {{ next_level = right; }}
                            }}
                            cursor = next;
                        }}
                        items.push("null".to_string());
                        level = next_level;
                    }}
                    while items.last().map_or(false, |value| value == "null") {{ items.pop(); }}
                    format!("[{{}}]", items.join(","))
                }}
                """
            )
            if return_type.get("kind") == "next_tree":
                result_expression = "Ok(openoj_next_tree_json(&openoj_actual))"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "next_tree":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|tree| openoj_next_tree_json(tree))"
                    ".collect::<Vec<String>>().join(\",\")))"
                )
        if "circular_list" in structs or "alias_list" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn shared_list(&mut self) -> Result<Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>>, String> {{
                        if self.take(1)?[0] == 0 {{ return Ok(None); }}
                        let length = self.u32()? as usize;
                        let mut head: Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>> = None;
                        let mut tail: Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>> = None;
                        for _ in 0..length {{
                            let node = std::rc::Rc::new(std::cell::RefCell::new(SharedListNode {{ val: {item_read}, next: None }}));
                            if let Some(previous) = tail.clone() {{ previous.borrow_mut().next = Some(node.clone()); }} else {{ head = Some(node.clone()); }}
                            tail = Some(node);
                        }}
                        Ok(head)
                    }}
                }}
                """
            )
        if "circular_list" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn circular_list(&mut self) -> Result<Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>>, String> {{
                        // The decoder closes the ring (tail.next = head)
                        // exactly like the harness languages, so solutions
                        // always see a real ring.
                        let length = self.u32()? as usize;
                        if length == 0 {{ return Ok(None); }}
                        let head = std::rc::Rc::new(std::cell::RefCell::new(SharedListNode {{ val: {item_read}, next: None }}));
                        let mut tail = head.clone();
                        for _ in 1..length {{
                            let node = std::rc::Rc::new(std::cell::RefCell::new(SharedListNode {{ val: {item_read}, next: None }}));
                            tail.borrow_mut().next = Some(node.clone());
                            tail = node;
                        }}
                        tail.borrow_mut().next = Some(head.clone());
                        Ok(Some(head))
                    }}
                }}
                fn openoj_circular_json(head: &Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>>) -> Result<String, String> {{
                    let head = match head {{ Some(node) => node.clone(), None => return Ok("[]".to_string()) }};
                    let mut items: Vec<String> = Vec::new();
                    let mut current = Some(head.clone());
                    for _ in 0..(1 << 20) {{
                        let node = current.clone().ok_or("Circular list is not closed")?;
                        items.push(node.borrow().val.to_string());
                        let next = node.borrow().next.clone();
                        match next {{
                            Some(next_node) if std::rc::Rc::ptr_eq(&next_node, &head) => return Ok(format!("[{{}}]", items.join(","))),
                            Some(next_node) => current = Some(next_node),
                            None => return Err("Circular list is not closed".into()),
                        }}
                    }}
                    Err("Circular list exceeds the walk bound".into())
                }}
                """
            )
            if return_type.get("kind") == "circular_list":
                result_expression = "Ok(openoj_circular_json(&openoj_actual)?)"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "circular_list":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|part| openoj_circular_json(part))"
                    ".collect::<Result<Vec<String>, String>>()?.join(\",\")))"
                )
        if "doubly_circular" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn doubly_circular(&mut self) -> Result<Option<std::rc::Rc<std::cell::RefCell<NodeWithNext>>>, String> {{
                        // LC 426: left is prev, right is next; the ring is
                        // read open (head.left unset) and the serializer
                        // verifies the solution closed it.
                        let length = self.u32()? as usize;
                        if length == 0 {{ return Ok(None); }}
                        let head = std::rc::Rc::new(std::cell::RefCell::new(NodeWithNext {{ val: {item_read}, left: None, right: None, next: None, parent: None }}));
                        let mut tail = head.clone();
                        for _ in 1..length {{
                            let node = std::rc::Rc::new(std::cell::RefCell::new(NodeWithNext {{ val: {item_read}, left: None, right: None, next: None, parent: None }}));
                            node.borrow_mut().left = Some(tail.clone());
                            tail.borrow_mut().right = Some(node.clone());
                            tail = node;
                        }}
                        Ok(Some(head))
                    }}
                }}
                fn openoj_doubly_json(head: &Option<std::rc::Rc<std::cell::RefCell<NodeWithNext>>>) -> Result<String, String> {{
                    let head = match head {{ Some(node) => node.clone(), None => return Ok("[]".to_string()) }};
                    let mut items: Vec<String> = Vec::new();
                    let mut previous: Option<std::rc::Rc<std::cell::RefCell<NodeWithNext>>> = None;
                    let mut current = Some(head.clone());
                    for _ in 0..(1 << 20) {{
                        let node = current.clone().ok_or("Doubly linked list is not closed")?;
                        if let Some(previous_node) = &previous {{
                            let linked = node.borrow().left.as_ref().map_or(false, |value| std::rc::Rc::ptr_eq(value, previous_node));
                            if !linked {{ return Err("Doubly linked list is not properly linked".into()); }}
                        }}
                        items.push(node.borrow().val.to_string());
                        previous = Some(node.clone());
                        let next = node.borrow().right.clone();
                        match next {{
                            Some(next_node) if std::rc::Rc::ptr_eq(&next_node, &head) => {{
                                let closed = head.borrow().left.as_ref().map_or(false, |value| std::rc::Rc::ptr_eq(value, &node));
                                if !closed {{ return Err("Doubly linked list is not properly linked".into()); }}
                                return Ok(format!("[{{}}]", items.join(",")));
                            }}
                            Some(next_node) => current = Some(next_node),
                            None => return Err("Doubly linked list is not closed".into()),
                        }}
                    }}
                    Err("Doubly linked list exceeds the walk bound".into())
                }}
                """
            )
            if return_type.get("kind") == "doubly_circular":
                result_expression = "Ok(openoj_doubly_json(&openoj_actual)?)"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "doubly_circular":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|part| openoj_doubly_json(part))"
                    ".collect::<Result<Vec<String>, String>>()?.join(\",\")))"
                )
        if "multi_list" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn multi_list(&mut self) -> Result<Option<std::rc::Rc<std::cell::RefCell<MultiListNode>>>, String> {{
                        // One chain: u32 n, then per node the value, a child
                        // flag, and the flagged child's own chain. Every
                        // chain (top and nested) gets its prev links set.
                        let length = self.u32()? as usize;
                        let mut head: Option<std::rc::Rc<std::cell::RefCell<MultiListNode>>> = None;
                        let mut tail: Option<std::rc::Rc<std::cell::RefCell<MultiListNode>>> = None;
                        for _ in 0..length {{
                            let node = std::rc::Rc::new(std::cell::RefCell::new(MultiListNode {{ val: {item_read}, prev: None, next: None, child: None }}));
                            if let Some(previous) = tail.clone() {{
                                previous.borrow_mut().next = Some(node.clone());
                                node.borrow_mut().prev = Some(previous);
                            }} else {{
                                head = Some(node.clone());
                            }}
                            tail = Some(node.clone());
                            if self.take(1)?[0] == 1 {{ node.borrow_mut().child = self.multi_list()?; }}
                        }}
                        Ok(head)
                    }}
                }}
                fn openoj_multi_json(head: &Option<std::rc::Rc<std::cell::RefCell<MultiListNode>>>) -> Result<String, String> {{
                    // A flattened result must be a clean doubly chain: every
                    // prev back-link set, no child left (LC 430 order is the
                    // solution's job — this walks the flat chain).
                    let mut items: Vec<String> = Vec::new();
                    let mut previous: Option<std::rc::Rc<std::cell::RefCell<MultiListNode>>> = None;
                    let mut current = head.clone();
                    for _ in 0..(1 << 20) {{
                        let node = match current {{ Some(node) => node, None => return Ok(format!("[{{}}]", items.join(","))) }};
                        let linked = match (node.borrow().prev.clone(), previous.clone()) {{
                            (None, None) => true,
                            (Some(value), Some(previous_node)) => std::rc::Rc::ptr_eq(&value, &previous_node),
                            _ => false,
                        }};
                        if !linked || node.borrow().child.is_some() {{
                            return Err("Flattened list is not properly linked".into());
                        }}
                        items.push(node.borrow().val.to_string());
                        previous = Some(node.clone());
                        current = node.borrow().next.clone();
                    }}
                    Err("Flattened list exceeds the walk bound".into())
                }}
                """
            )
            if return_type.get("kind") == "multi_list":
                result_expression = "Ok(openoj_multi_json(&openoj_actual)?)"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "multi_list":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|part| openoj_multi_json(part))"
                    ".collect::<Result<Vec<String>, String>>()?.join(\",\")))"
                )
        if "alias_list" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                fn openoj_alias_json(node: &Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>>, input_nodes: &[*const std::cell::RefCell<SharedListNode>]) -> Result<String, String> {{
                    // LC 160: the intersection is by identity — the result
                    // must be a node taken from the input lists, and the
                    // wire is the shared tail's values.
                    let node = match node {{ Some(node) => node, None => return Ok("[]".to_string()) }};
                    if !input_nodes.contains(&std::rc::Rc::as_ptr(node)) {{
                        return Err("Returned node is not part of the input lists".into());
                    }}
                    let mut items: Vec<String> = Vec::new();
                    let mut current = Some(node.clone());
                    while let Some(walk) = current {{
                        items.push(walk.borrow().val.to_string());
                        current = walk.borrow().next.clone();
                    }}
                    Ok(format!("[{{}}]", items.join(",")))
                }}
                """
            )
            if return_type.get("kind") == "alias_list":
                result_expression = "Ok(openoj_alias_json(&openoj_actual, &openoj_input_nodes_alias.borrow())?)"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "alias_list":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|part| openoj_alias_json(part, &openoj_input_nodes_alias.borrow()))"
                    ".collect::<Result<Vec<String>, String>>()?.join(\",\")))"
                )
        if "graph" in structs:
            # The class is the using problem's provided/ source (LC 133);
            # the rendered name below is the manifest's class name.
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn graph(&mut self) -> Result<Option<std::rc::Rc<std::cell::RefCell<{graph_class}>>>, String> {{
                        let count = self.u32()? as usize;
                        if count == 0 {{ return Ok(None); }}
                        let nodes: Vec<std::rc::Rc<std::cell::RefCell<{graph_class}>>> = (0..count)
                            .map(|index| std::rc::Rc::new(std::cell::RefCell::new({graph_class}::new(index as i32 + 1))))
                            .collect();
                        for index in 0..count {{
                            let degree = self.u32()? as usize;
                            for _ in 0..degree {{
                                let value = {item_read} + 1;
                                if value < 1 || value as usize > count {{ return Err("Graph neighbor is out of range".into()); }}
                                nodes[index].borrow_mut().neighbors.push(nodes[(value - 1) as usize].clone());
                            }}
                        }}
                        Ok(Some(nodes[0].clone()))
                    }}
                }}
                fn openoj_graph_json(root: &Option<std::rc::Rc<std::cell::RefCell<{graph_class}>>>, input_nodes: &[*const std::cell::RefCell<{graph_class}>]) -> Result<String, String> {{
                    // Rows ordered by node value; neighbor order is
                    // normalized (sorted) since LC treats adjacency order
                    // as irrelevant.
                    let mut visited: Vec<std::rc::Rc<std::cell::RefCell<{graph_class}>>> = Vec::new();
                    if let Some(start) = root {{
                        let mut queue: std::collections::VecDeque<std::rc::Rc<std::cell::RefCell<{graph_class}>>> = std::collections::VecDeque::new();
                        queue.push_back(start.clone());
                        while let Some(node) = queue.pop_front() {{
                            if visited.iter().any(|value| std::rc::Rc::ptr_eq(value, &node)) {{ continue; }}
                            visited.push(node.clone());
                            let neighbors = node.borrow().neighbors.clone();
                            for neighbor in neighbors {{ queue.push_back(neighbor); }}
                        }}
                    }}
                    for node in &visited {{
                        if input_nodes.contains(&std::rc::Rc::as_ptr(node)) {{
                            return Err("Returned graph shares nodes with the input graph".into());
                        }}
                    }}
                    visited.sort_by_key(|node| node.borrow().val);
                    let rows: Result<Vec<String>, String> = visited.iter().map(|node| {{
                        let mut values: Vec<i32> = node.borrow().neighbors.iter().map(|neighbor| neighbor.borrow().val).collect();
                        values.sort();
                        Ok(format!("[{{}}]", values.iter().map(|value| value.to_string()).collect::<Vec<String>>().join(",")))
                    }}).collect();
                    Ok(format!("[{{}}]", rows?.join(",")))
                }}
                """
            )
            if return_type.get("kind") == "graph":
                result_expression = "Ok(openoj_graph_json(&openoj_actual, &openoj_input_nodes_graph.borrow())?)"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "graph":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|part| openoj_graph_json(part, &openoj_input_nodes_graph.borrow()))"
                    ".collect::<Result<Vec<String>, String>>()?.join(\",\")))"
                )
        if "random_list" in structs:
            struct_codecs += textwrap.dedent(
                f"""
                impl OpenOJReader {{
                    fn random_list(&mut self) -> Result<Option<std::rc::Rc<std::cell::RefCell<{random_class}>>>, String> {{
                        let count = self.u32()? as usize;
                        if count == 0 {{ return Ok(None); }}
                        let mut nodes: Vec<std::rc::Rc<std::cell::RefCell<{random_class}>>> = Vec::with_capacity(count);
                        let mut targets: Vec<u32> = Vec::with_capacity(count);
                        // Each row carries [val, random] together.
                        for _ in 0..count {{
                            nodes.push(std::rc::Rc::new(std::cell::RefCell::new({random_class}::new({item_read}))));
                            targets.push(self.u32()?);
                        }}
                        for index in 0..count.saturating_sub(1) {{
                            nodes[index].borrow_mut().next = Some(nodes[index + 1].clone());
                        }}
                        for (index, target) in targets.into_iter().enumerate() {{
                            if target == 0xFFFF_FFFF {{ continue; }}
                            if target as usize >= count {{ return Err("Random pointer target is out of range".into()); }}
                            nodes[index].borrow_mut().random = Some(nodes[target as usize].clone());
                        }}
                        Ok(Some(nodes[0].clone()))
                    }}
                }}
                fn openoj_random_json(head: &Option<std::rc::Rc<std::cell::RefCell<{random_class}>>>, input_nodes: &[*const std::cell::RefCell<{random_class}>]) -> Result<String, String> {{
                    let mut nodes: Vec<std::rc::Rc<std::cell::RefCell<{random_class}>>> = Vec::new();
                    let mut current = head.clone();
                    while let Some(node) = current {{
                        if nodes.iter().any(|value| std::rc::Rc::ptr_eq(value, &node)) {{
                            return Err("Random list has a cycle in next".into());
                        }}
                        nodes.push(node.clone());
                        current = node.borrow().next.clone();
                    }}
                    for node in &nodes {{
                        if input_nodes.contains(&std::rc::Rc::as_ptr(node)) {{
                            return Err("Returned list shares nodes with the input list".into());
                        }}
                    }}
                    let rows: Result<Vec<String>, String> = nodes.iter().map(|node| {{
                        let borrowed = node.borrow();
                        let random = borrowed.random.clone();
                        match random {{
                            None => Ok(format!("[{{}},null]", borrowed.val)),
                            Some(target) => {{
                                let index = nodes.iter().position(|value| std::rc::Rc::ptr_eq(value, &target));
                                match index {{
                                    Some(position) => Ok(format!("[{{}},{{}}]", borrowed.val, position)),
                                    None => Err("Random pointer leaves the returned list".into()),
                                }}
                            }}
                        }}
                    }}).collect();
                    Ok(format!("[{{}}]", rows?.join(",")))
                }}
                """
            )
            if return_type.get("kind") == "random_list":
                result_expression = "Ok(openoj_random_json(&openoj_actual, &openoj_input_nodes_random.borrow())?)"
            if return_type.get("kind") == "array" and return_type.get("items", {}).get("kind") == "random_list":
                result_expression = (
                    "Ok(format!(\"[{}]\", openoj_actual.iter()"
                    ".map(|part| openoj_random_json(part, &openoj_input_nodes_random.borrow()))"
                    ".collect::<Result<Vec<String>, String>>()?.join(\",\")))"
                )
        if "struct" in structs:
            def _struct_reader(spec: dict[str, Any]) -> str:
                fields = spec.get("fields") or []
                class_name = spec["class"]
                assignments = ", ".join(
                    f"{field['name']}: {_read_expression(field['value_type'], 'self')}"
                    for field in fields
                )
                return (
                    f"    fn read{_snake_case(class_name)}(&mut self) -> Result<{class_name}, String> {{\n"
                    f"        Ok({class_name} {{ {assignments} }})\n"
                    "    }\n"
                )

            struct_specs: dict[str, Any] = {}

            def _collect(spec: Any) -> None:
                if not isinstance(spec, dict):
                    return
                if spec.get("kind") == "struct":
                    struct_specs.setdefault(spec["class"], spec)
                elif spec.get("kind") == "array":
                    _collect(spec.get("items"))

            for parameter in invocation.get("parameters", []):
                _collect(parameter.get("value_type") if isinstance(parameter, dict) else None)
            readers = "".join(_struct_reader(spec) for _, spec in sorted(struct_specs.items()))
            struct_codecs += "impl OpenOJReader {\n" + readers + "}\n"

        # Alias splices need the aliased list's nodes; clone checks need
        # every input node registered — read the parameters with that
        # bookkeeping inline (one registration per list-shaped parameter).
        aliased_indexes = sorted(
            {
                spec["alias"]
                for spec in parameters
                if spec.get("kind") == "alias_list"
            }
        )
        input_locals = ""
        if "alias_list" in structs:
            input_locals += (
                "    let openoj_input_nodes_alias: std::cell::RefCell<Vec<*const std::cell::RefCell<SharedListNode>>> = "
                "std::cell::RefCell::new(Vec::new());\n"
            )
        if "graph" in structs:
            input_locals += (
                f"    let openoj_input_nodes_graph: std::cell::RefCell<Vec<*const std::cell::RefCell<{graph_class}>>> = "
                "std::cell::RefCell::new(Vec::new());\n"
            )
        if "random_list" in structs:
            input_locals += (
                f"    let openoj_input_nodes_random: std::cell::RefCell<Vec<*const std::cell::RefCell<{random_class}>>> = "
                "std::cell::RefCell::new(Vec::new());\n"
            )

        def declaration(index: int, spec: dict[str, Any]) -> str:
            if spec.get("kind") == "alias_list":
                aliased = f"openoj_arg_{spec['alias']}_nodes"
                return textwrap.dedent(
                    f"""
                    let openoj_arg_{index}: Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>> = {{
                        let count = openoj_reader.u32()? as usize;
                        let mut head: Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>> = None;
                        let mut tail: Option<std::rc::Rc<std::cell::RefCell<SharedListNode>>> = None;
                        let mut prefix: Vec<std::rc::Rc<std::cell::RefCell<SharedListNode>>> = Vec::with_capacity(count);
                        for _ in 0..count {{
                            let node = std::rc::Rc::new(std::cell::RefCell::new(SharedListNode {{ val: openoj_reader.i32()?, next: None }}));
                            if let Some(previous) = tail.clone() {{
                                previous.borrow_mut().next = Some(node.clone());
                            }} else {{
                                head = Some(node.clone());
                            }}
                            tail = Some(node.clone());
                            prefix.push(node);
                        }}
                        let splice_at = openoj_reader.u32()? as usize;
                        if let Some(target) = {aliased}.get(splice_at) {{
                            // Real shared nodes: the prefix's last node (or
                            // the head when the prefix is empty) joins the
                            // aliased list at the splice point.
                            match tail.clone() {{
                                Some(previous) => {{ previous.borrow_mut().next = Some(target.clone()); }}
                                None => {{ head = Some(target.clone()); }}
                            }}
                        }}
                        for node in &prefix {{
                            openoj_input_nodes_alias.borrow_mut().push(std::rc::Rc::as_ptr(node));
                        }}
                        let mut walk = head.clone();
                        while let Some(node) = walk {{
                            openoj_input_nodes_alias.borrow_mut().push(std::rc::Rc::as_ptr(&node));
                            walk = node.borrow().next.clone();
                        }}
                        head
                    }};
                    """
                ).rstrip()
            aliased = spec.get("kind") == "linked_list" and index in aliased_indexes
            # An aliased linked_list renders as the shared-ownership node
            # (the alias_list reader splices real nodes between the lists),
            # so it decodes through the shared reader, not the Box one.
            read_expression = "openoj_reader.shared_list()?" if aliased else _read_expression(spec)
            lines = [
                f"    let openoj_arg_{index}: {rust_parameter_type(invocation, index, spec)} = {read_expression};"
            ]
            if aliased:
                lines.append(
                    f"    let openoj_arg_{index}_nodes: Vec<std::rc::Rc<std::cell::RefCell<SharedListNode>>> = {{"
                )
                lines.append("        let mut nodes = Vec::new();")
                lines.append(f"        let mut current = openoj_arg_{index}.clone();")
                lines.append("        while let Some(node) = current {")
                lines.append("            openoj_input_nodes_alias.borrow_mut().push(std::rc::Rc::as_ptr(&node));")
                lines.append("            nodes.push(node.clone());")
                lines.append("            current = node.borrow().next.clone();")
                lines.append("        }")
                lines.append("        nodes")
                lines.append("    };")
            if spec.get("kind") == "graph":
                lines.append("    {")
                lines.append(
                    "        let mut queue: std::collections::VecDeque<std::rc::Rc<std::cell::RefCell<"
                    f"{graph_class}>>> = std::collections::VecDeque::new();"
                )
                lines.append(f"        if let Some(start) = openoj_arg_{index}.clone() {{ queue.push_back(start); }}")
                lines.append("        while let Some(node) = queue.pop_front() {")
                lines.append(
                    "            if openoj_input_nodes_graph.borrow().iter().any(|value| *value == std::rc::Rc::as_ptr(&node)) { continue; }"
                )
                lines.append("            openoj_input_nodes_graph.borrow_mut().push(std::rc::Rc::as_ptr(&node));")
                lines.append("            let neighbors = node.borrow().neighbors.clone();")
                lines.append("            for neighbor in neighbors { queue.push_back(neighbor); }")
                lines.append("        }")
                lines.append("    }")
            if spec.get("kind") == "random_list":
                lines.append("    {")
                lines.append(f"        let mut current = openoj_arg_{index}.clone();")
                lines.append("        while let Some(node) = current {")
                lines.append(
                    "            openoj_input_nodes_random.borrow_mut().push(std::rc::Rc::as_ptr(&node));"
                )
                lines.append("            current = node.borrow().next.clone();")
                lines.append("        }")
                lines.append("    }")
            return "\n".join(lines)

        declarations = "\n".join(
            declaration(index, spec) for index, spec in enumerate(parameters)
        )
        arguments = ", ".join(f"openoj_arg_{index}" for index in range(len(parameters)))
        source = assembly_source + textwrap.dedent(
            f"""
            use std::fmt::Write as OpenOJFmtWrite;
            use std::io::Read as OpenOJIoRead;

            pub struct Solution;

            {code}

            struct OpenOJReader {{ data: Vec<u8>, offset: usize }}
            impl OpenOJReader {{
                fn take(&mut self, count: usize) -> Result<&[u8], String> {{
                    if count > self.data.len().saturating_sub(self.offset) {{ return Err("Truncated judge input".into()); }}
                    let start = self.offset;
                    self.offset += count;
                    Ok(&self.data[start..self.offset])
                }}
                fn u32(&mut self) -> Result<u32, String> {{ Ok(u32::from_be_bytes(self.take(4)?.try_into().unwrap())) }}
                fn i32(&mut self) -> Result<i32, String> {{ Ok(i32::from_be_bytes(self.take(4)?.try_into().unwrap())) }}
                fn i64(&mut self) -> Result<i64, String> {{ Ok(i64::from_be_bytes(self.take(8)?.try_into().unwrap())) }}
                fn number(&mut self) -> Result<f64, String> {{ Ok(f64::from_be_bytes(self.take(8)?.try_into().unwrap())) }}
                fn boolean(&mut self) -> Result<bool, String> {{ let value = self.take(1)?[0]; if value > 1 {{ return Err("Invalid boolean input".into()); }} Ok(value == 1) }}
                fn text(&mut self) -> Result<String, String> {{ let length = self.u32()? as usize; String::from_utf8(self.take(length)?.to_vec()).map_err(|_| "Invalid UTF-8 input".into()) }}
                fn array<T, F>(&mut self, mut read: F) -> Result<Vec<T>, String> where F: FnMut(&mut Self) -> Result<T, String> {{
                    let length = self.u32()? as usize;
                    let mut values = Vec::with_capacity(length);
                    for _ in 0..length {{ values.push(read(self)?); }}
                    Ok(values)
                }}
                fn finished(&self) -> Result<(), String> {{ if self.offset == self.data.len() {{ Ok(()) }} else {{ Err("Trailing judge input".into()) }} }}
            }}
{struct_codecs}
            trait OpenOJToJson {{ fn openoj_json(&self) -> Result<String, String>; }}
            impl OpenOJToJson for i32 {{ fn openoj_json(&self) -> Result<String, String> {{ Ok(self.to_string()) }} }}
            impl OpenOJToJson for i64 {{ fn openoj_json(&self) -> Result<String, String> {{ Ok(self.to_string()) }} }}
            impl OpenOJToJson for bool {{ fn openoj_json(&self) -> Result<String, String> {{ Ok(self.to_string()) }} }}
            impl OpenOJToJson for f64 {{ fn openoj_json(&self) -> Result<String, String> {{ if self.is_finite() {{ Ok(self.to_string()) }} else {{ Err("Non-finite return value".into()) }} }} }}
            impl OpenOJToJson for String {{ fn openoj_json(&self) -> Result<String, String> {{ Ok(openoj_json_string(self)) }} }}
            impl<T: OpenOJToJson> OpenOJToJson for Vec<T> {{
                fn openoj_json(&self) -> Result<String, String> {{
                    let values: Result<Vec<String>, String> = self.iter().map(|value| value.openoj_json()).collect();
                    Ok(format!("[{{}}]", values?.join(",")))
                }}
            }}
            fn openoj_json_string(value: &str) -> String {{
                let mut output = String::from("\\\"");
                for character in value.chars() {{
                    match character {{
                        '\\"' => output.push_str("\\\\\\\""),
                        '\\\\' => output.push_str("\\\\\\\\"),
                        '\\n' => output.push_str("\\\\n"),
                        '\\r' => output.push_str("\\\\r"),
                        '\\t' => output.push_str("\\\\t"),
                        '\\u{{0008}}' => output.push_str("\\\\b"),
                        '\\u{{000c}}' => output.push_str("\\\\f"),
                        value if value < '\\u{{0020}}' => {{ let _ = write!(output, "\\\\u{{:04x}}", value as u32); }},
                        value => output.push(value),
                    }}
                }}
                output.push('\\"');
                output
            }}

            fn openoj_run() -> Result<String, String> {{
                let mut bytes = Vec::new();
                std::io::stdin().read_to_end(&mut bytes).map_err(|error| error.to_string())?;
                let mut openoj_reader = OpenOJReader {{ data: bytes, offset: 0 }};
            {input_locals}
            {declarations}
                openoj_reader.finished()?;
                let openoj_actual = Solution::{method}({arguments});
                // Bound to a local so any Ref temporary borrowed from the
                // input-node registries drops before openoj_run's locals.
                let openoj_output = {result_expression};
                openoj_output
            }}

            fn openoj_emit(line: &str) {{
                // Judge protocol prefers the dedicated fd so submission code
                // cannot forge verdicts on stdout; stdout is the fallback.
                use std::io::Write;
                use std::os::unix::io::FromRawFd;
                let mut channel = unsafe {{ std::fs::File::from_raw_fd(63) }};
                if write!(channel, "{{}}\\n", line).is_ok() {{
                    return;
                }}
                println!("{{}}", line);
            }}

            fn main() {{
                let response = std::panic::catch_unwind(openoj_run);
                match response {{
                    Ok(Ok(actual)) => openoj_emit(&format!("__OPENOJ_RESULT__{{{{\\\"status\\\":\\\"completed\\\",\\\"actual\\\":{{}}}}}}", actual)),
                    Ok(Err(error)) => openoj_emit(&format!("__OPENOJ_RESULT__{{{{\\\"status\\\":\\\"runtime_error\\\",\\\"error\\\":{{}}}}}}", openoj_json_string(&error))),
                    Err(_) => openoj_emit("__OPENOJ_RESULT__{{{{\\\"status\\\":\\\"runtime_error\\\",\\\"error\\\":\\\"Solution panicked\\\"}}}}"),
                }}
            }}
            """
        ).lstrip()
        source_path = job_root / "main.rs"
        executable = job_root / "solution"
        source_path.write_text(source, encoding="utf-8")
        source_path.chmod(0o444)
        self.compile(
            job_root,
            (
                self.compiler_path,
                "--edition=2021",
                "-C",
                "opt-level=2",
                "-C",
                "debuginfo=0",
                "-C",
                "strip=symbols",
                "-o",
                str(executable),
                str(source_path),
            ),
            executable,
            {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "TMPDIR": "/tmp"},
        )
        return PreparedProgram(
            command=(str(executable),),
            environment={
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "TMPDIR": str(scratch),
                "RUST_BACKTRACE": "0",
            },
        )

    def encode_case(self, invocation: dict[str, Any], case_input: Any) -> bytes:
        if invocation.get("type") == "interactive":
            from .typed import encode_interactive_case
            return encode_interactive_case(invocation, case_input)
        if invocation.get("type") == "design":
            from .design_interactive import encode_design_case
            return encode_design_case(invocation, case_input)
        return encode_case(invocation, case_input, self.language)
