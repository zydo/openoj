"""LeetCode-compatible Python structures and JSON codecs.

The wire representations follow the conventions in the user-provided sibling
judge: linked lists are value arrays, binary trees are trimmed level-order
arrays, and N-ary trees use ``null`` delimiters between child groups.
"""

from collections import deque
from typing import Any


class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


class Node:
    def __init__(self, val=None, children=None):
        self.val = val
        self.children = children if children is not None else []


class NestedInteger:
    def __init__(self, value=None):
        if isinstance(value, list):
            self._list = [NestedInteger(item) for item in value]
            self._integer = None
        else:
            self._list = None
            self._integer = value

    def isInteger(self):
        return self._list is None

    def getInteger(self):
        return self._integer

    def getList(self):
        return self._list


class HtmlParser:
    def __init__(self, url_to_urls):
        self._map = url_to_urls

    def getUrls(self, url):
        return list(self._map.get(url, []))


def _parse_list_node(data):
    if not data:
        return None
    head = ListNode(data[0])
    current = head
    for value in data[1:]:
        current.next = ListNode(value)
        current = current.next
    return head


def _serialize_list_node(head):
    values = []
    current = head
    while current:
        values.append(current.val)
        current = current.next
    return values


def _parse_tree_node(data):
    if not data:
        return None
    root = TreeNode(data[0])
    queue = deque([root])
    index = 1
    while queue and index < len(data):
        node = queue.popleft()
        if index < len(data) and data[index] is not None:
            node.left = TreeNode(data[index])
            queue.append(node.left)
        index += 1
        if index < len(data) and data[index] is not None:
            node.right = TreeNode(data[index])
            queue.append(node.right)
        index += 1
    return root


def _serialize_tree_node(root):
    if root is None:
        return []
    output = []
    queue = deque([root])
    while queue:
        node = queue.popleft()
        if node is None:
            output.append(None)
            continue
        output.append(node.val)
        queue.extend((node.left, node.right))
    while output and output[-1] is None:
        output.pop()
    return output


def _parse_nary_tree(data):
    if not data:
        return None
    root = Node(data[0])
    queue = deque([root])
    index = 2
    while queue and index < len(data):
        parent = queue.popleft()
        while index < len(data) and data[index] is not None:
            child = Node(data[index])
            parent.children.append(child)
            queue.append(child)
            index += 1
        index += 1
    return root


def _serialize_nary_tree(root):
    if root is None:
        return []
    output = [root.val, None]
    queue = deque([root])
    while queue:
        parent = queue.popleft()
        for child in parent.children:
            output.append(child.val)
            queue.append(child)
        output.append(None)
    while output and output[-1] is None:
        output.pop()
    return output


def decode(value: Any, codec: str) -> Any:
    if codec == "json":
        return value
    if codec == "list_node":
        return _parse_list_node(value)
    if codec == "tree_node":
        return _parse_tree_node(value)
    if codec == "list_node_array":
        return [_parse_list_node(item) for item in value]
    if codec == "tree_node_array":
        return [_parse_tree_node(item) for item in value]
    if codec == "nary_tree":
        return _parse_nary_tree(value)
    if codec == "nested_integer_list":
        return [NestedInteger(item) for item in value]
    if codec == "html_parser":
        urls = value["urls"]
        mapping = {url: [] for url in urls}
        for left, right in value["edges"]:
            mapping[urls[left]].append(urls[right])
        return HtmlParser(mapping)
    raise ValueError(f"Unsupported input codec: {codec}")


def encode(value: Any, codec: str) -> Any:
    if codec == "json":
        return value
    if codec == "list_node":
        return _serialize_list_node(value)
    if codec == "tree_node":
        return _serialize_tree_node(value)
    if codec == "list_node_array":
        return [_serialize_list_node(item) for item in value]
    if codec == "tree_node_array":
        return [_serialize_tree_node(item) for item in value]
    if codec == "nary_tree":
        return _serialize_nary_tree(value)
    raise ValueError(f"Unsupported output codec: {codec}")
