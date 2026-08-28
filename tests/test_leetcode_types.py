import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runner"))

import leetcode_types as lt  # noqa: E402
from leetcode_types import (  # noqa: E402
    GraphNode,
    ListNode,
    MultiListNode,
    NestedInteger,
    NodeWithNext,
    QuadNode,
    RandomListNode,
    decode,
    encode,
)


class LeetCodeCodecTests(unittest.TestCase):
    def test_linked_list_round_trip(self) -> None:
        for sample in ([], [1], [1, 2, 3], [-4, 0, 8]):
            with self.subTest(sample=sample):
                self.assertEqual(sample, encode(decode(sample, "list_node"), "list_node"))

    def test_binary_tree_round_trip(self) -> None:
        samples = ([], [1], [1, 2, 3], [1, None, 2, None, 3], [1, 2, 3, None, None, 4, 5])
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(sample, encode(decode(sample, "tree_node"), "tree_node"))

    def test_nary_tree_round_trip(self) -> None:
        samples = ([], [1], [1, None, 3, 2, 4, None, 5, 6])
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(sample, encode(decode(sample, "nary_tree"), "nary_tree"))

    def test_quad_tree_serializes_a_non_leaf_val_as_false(self) -> None:
        root = QuadNode(False, False)
        root.topLeft = QuadNode(True, True)
        root.topRight = QuadNode(True, True)
        root.bottomLeft = QuadNode(True, True)
        root.bottomRight = QuadNode(False, True)
        self.assertEqual(
            [[0, 0], [1, 1], [1, 1], [1, 1], [1, 0]], lt._serialize_quad_tree(root)
        )
        # Round trip through the display wire; any internal val a solution
        # leaves on inner nodes is normalized away on both sides.
        messy = QuadNode(7, False)
        messy.topLeft = QuadNode(0, True)
        messy.topRight = QuadNode(1, True)
        messy.bottomLeft = QuadNode(0, True)
        messy.bottomRight = QuadNode(1, True)
        display = lt._serialize_quad_tree(messy)
        self.assertEqual([[0, 0], [1, 0], [1, 1], [1, 0], [1, 1]], display)
        self.assertEqual(display, lt._serialize_quad_tree(lt._parse_quad_tree(display)))

    def test_nested_integer_round_trip(self) -> None:
        for sample in (1, [1, 2], [1, [2, [3]], 4], []):
            with self.subTest(sample=sample):
                node = lt._parse_nested(sample)
                self.assertEqual(sample, lt._serialize_nested(node))

    def test_next_tree_parent_wiring_and_level_serialization(self) -> None:
        root = lt._parse_next_tree([1, 2, 3, 4, 5])
        self.assertIs(root.parent, None)
        self.assertIs(root.left.parent, root)
        self.assertIs(root.right.parent, root)
        # The solution wires next within each level; the serializer reads
        # each level through the next chain.
        root.next = None
        left_level, right_level = root.left, root.right
        left_level.next = right_level
        self.assertEqual([1, None, 2, 3, None, 4], lt._serialize_next_tree(root))
        # A no-op (next all null) serializes short — 3 and 5 are only
        # reachable through next — so an untouched tree cannot pass as
        # connected.
        untouched = lt._parse_next_tree([1, 2, 3, 4, 5])
        self.assertEqual([1, None, 2, None, 4], lt._serialize_next_tree(untouched))

    def test_circular_list_closes_and_requires_a_closed_ring(self) -> None:
        head = lt._parse_circular_list([1, 2, 3])
        self.assertIs(head.next.next.next, head)
        self.assertEqual([1, 2, 3], lt._serialize_circular_list(head))
        self.assertEqual([], lt._serialize_circular_list(None))
        with self.assertRaisesRegex(ValueError, "not closed"):
            lt._serialize_circular_list(lt._parse_list_node([1, 2]))

    def test_doubly_circular_requires_back_links(self) -> None:
        nodes = [NodeWithNext(3), NodeWithNext(2), NodeWithNext(1)]
        for left, right in zip(nodes, nodes[1:]):
            left.right = right
            right.left = left
        nodes[-1].right = nodes[0]
        nodes[0].left = nodes[-1]
        self.assertEqual([3, 2, 1], lt._serialize_doubly_circular(nodes[0]))
        nodes[1].left = None
        with self.assertRaisesRegex(ValueError, "properly linked"):
            lt._serialize_doubly_circular(nodes[0])

    def test_multi_list_decode_and_flattened_serialization(self) -> None:
        chain = {
            "values": [1, 2, 3],
            "children": [None, {"values": [7, 8], "children": [None, None]}, None],
        }
        head = lt._parse_multi_list(chain)
        self.assertIsNone(head.child)
        self.assertIs(head.next.child.val, 7)
        # The serializer judges the solution's flattened return: the child
        # chain spliced into next, prevs intact, no child pointers left.
        flat_values = [1, 7, 8, 2, 3]
        flat = [MultiListNode(value) for value in flat_values]
        for left, right in zip(flat, flat[1:]):
            left.next = right
            right.prev = left
        self.assertEqual(flat_values, lt._serialize_multi_list(flat[0]))
        # An unflattened child pointer is a serialization error, not silence.
        unflattened = MultiListNode(1)
        unflattened.child = MultiListNode(2)
        with self.assertRaisesRegex(ValueError, "properly linked"):
            lt._serialize_multi_list(unflattened)

    def test_alias_list_splices_shared_references(self) -> None:
        list_a = decode([4, 1, 8, 4, 5], "list_node")
        list_b = lt.parse_alias_list({"values": [5, 6, 1], "splice_at": 2}, list_a)
        shared = list_a.next.next
        self.assertIs(list_b.next.next.next, shared)
        self.assertIs(shared, lt._alias_head(list_a, 2))
        self.assertEqual([8, 4, 5], lt.serialize_alias_list(shared, list_a))
        self.assertEqual([], lt.serialize_alias_list(None, list_a))
        with self.assertRaisesRegex(ValueError, "not part of the aliased list"):
            lt.serialize_alias_list(ListNode(8), list_a)

    def test_graph_decodes_shared_nodes_and_rejects_input_identity(self) -> None:
        head = lt._parse_graph([[2, 4], [1, 3], [2, 4], [1, 3]])
        self.assertIsInstance(head.neighbors[0], GraphNode)
        nodes = lt.graph_nodes(head)
        self.assertEqual(4, len(nodes))
        # A cloned graph serializes to adjacency rows in val order.
        clones = {node.val: GraphNode(node.val) for node in nodes}
        for node in nodes:
            clones[node.val].neighbors = [clones[neighbor.val] for neighbor in node.neighbors]
        self.assertEqual(
            [[2, 4], [1, 3], [2, 4], [1, 3]],
            lt.serialize_graph(clones[1]),
        )
        with self.assertRaisesRegex(ValueError, "shares nodes"):
            lt.serialize_graph(head, nodes)

    def test_random_list_serializes_indices_and_rejects_input_identity(self) -> None:
        rows = [[7, None], [13, 0], [11, 4], [10, 2], [1, 0]]
        head = lt._parse_random_list(rows)
        self.assertIsNone(head.random)
        self.assertIs(head.next.random, head)
        nodes = lt.chain_nodes(head)
        cloned_head = lt._parse_random_list(rows)
        self.assertEqual(rows, lt.serialize_random_list(cloned_head))
        with self.assertRaisesRegex(ValueError, "shares nodes"):
            lt.serialize_random_list(head, nodes)


if __name__ == "__main__":
    unittest.main()

