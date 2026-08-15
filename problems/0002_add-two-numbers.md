# 2. Add Two Numbers

## Metadata

```json
{
  "schema_version": 1,
  "slug": "add-two-numbers",
  "difficulty": "H2",
  "tags": ["Linked List", "Math", "Recursion"]
}
```

## Description

You are given two non-empty linked lists representing two non-negative
integers. The digits are stored in reverse order, and each of their nodes
contains a single digit. Add the two numbers and return the sum as a linked
list.

You may assume the two numbers do not contain any leading zero, except the
number `0` itself.

### Example 1

```text
Input: l1 = [2,4,3], l2 = [5,6,4]
Output: [7,0,8]
Explanation: 342 + 465 = 807.
```

### Example 2

```text
Input: l1 = [0], l2 = [0]
Output: [0]
```

### Example 3

```text
Input: l1 = [9,9,9,9,9,9,9], l2 = [9,9,9,9]
Output: [8,9,9,9,0,0,0,1]
```

### Constraints

- The number of nodes in each linked list is in the range `[1, 100]`.
- `0 <= Node.val <= 9`
- It is guaranteed that the list represents a number that does not have
  leading zeros.

## Hints

```json
[
  "Track the carry as you walk both lists node by node, exactly like digit-by-digit addition on paper.",
  "The two lists may have different lengths; once one runs out, keep processing the longer one with the remaining carry.",
  "A final carry of 1 after both lists end still appends one more node."
]
```

## Invocation

```json
{
  "type": "function",
  "class_name": "Solution",
  "method": "addTwoNumbers",
  "parameters": [
    {
      "name": "l1",
      "codec": "list_node",
      "value_type": {
        "kind": "linked_list",
        "items": {"kind": "integer", "bits": 32}
      }
    },
    {
      "name": "l2",
      "codec": "list_node",
      "value_type": {
        "kind": "linked_list",
        "items": {"kind": "integer", "bits": 32}
      }
    }
  ],
  "return_codec": "list_node",
  "return_type": {
    "kind": "linked_list",
    "items": {"kind": "integer", "bits": 32}
  },
  "entrypoints": {
    "go": "addTwoNumbers",
    "rust": "add_two_numbers",
    "typescript": "addTwoNumbers"
  },
  "comparison": "exact"
}
```

## Limits

```json
{
  "time_ms": 1500,
  "memory_mb": 256,
  "output_kb": 64
}
```

## Languages

```json
{
  "python3": {
    "display_name": "Python 3",
    "monaco_language": "python",
    "version": "3.14.7",
    "enabled": true
  },
  "javascript": {
    "display_name": "JavaScript",
    "monaco_language": "javascript",
    "version": "Node 22.23.2",
    "enabled": true
  },
  "typescript": {
    "display_name": "TypeScript",
    "monaco_language": "typescript",
    "version": "TypeScript 7.0.2 / Node 22.23.2",
    "enabled": true
  },
  "java": {
    "display_name": "Java",
    "monaco_language": "java",
    "version": "JDK 21.0.12",
    "enabled": true
  },
  "cpp": {
    "display_name": "C++",
    "monaco_language": "cpp",
    "version": "G++ 14.2.0",
    "enabled": true
  },
  "go": {
    "display_name": "Go",
    "monaco_language": "go",
    "version": "Go 1.24.4",
    "enabled": true
  },
  "rust": {
    "display_name": "Rust",
    "monaco_language": "rust",
    "version": "Rust 1.85.0",
    "enabled": true
  }
}
```

## Starters

### python3

```python
from typing import List, Optional


class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


class Solution:
    def addTwoNumbers(self, l1: Optional[ListNode], l2: Optional[ListNode]) -> Optional[ListNode]:
        raise NotImplementedError("TODO")
```

### javascript

```javascript
/**
 * @param {ListNode} l1
 * @param {ListNode} l2
 * @return {ListNode}
 */
var addTwoNumbers = function(l1, l2) {
    throw new Error("TODO");
};
```

### typescript

```typescript
function addTwoNumbers(l1: ListNode | null, l2: ListNode | null): ListNode | null {
    throw new Error("TODO");
}
```

### java

```java
class Solution {
    public ListNode addTwoNumbers(ListNode l1, ListNode l2) {
        throw new UnsupportedOperationException("TODO");
    }
}
```

### cpp

```cpp
class Solution {
public:
    ListNode* addTwoNumbers(ListNode* l1, ListNode* l2) {
        throw logic_error("TODO");
    }
};
```

### go

```go
func addTwoNumbers(l1 *ListNode, l2 *ListNode) *ListNode {
    panic("TODO")
}
```

### rust

```rust
#[derive(PartialEq, Eq, Clone, Debug)]
pub struct ListNode {
    pub val: i32,
    pub next: Option<Box<ListNode>>,
}

impl Solution {
    pub fn add_two_numbers(l1: Option<Box<ListNode>>, l2: Option<Box<ListNode>>) -> Option<Box<ListNode>> {
        panic!("TODO")
    }
}
```

## Test Cases

### Public

```json
[
  {"input": [[2, 4, 3], [5, 6, 4]], "expected": [7, 0, 8]},
  {"input": [[0], [0]], "expected": [0]},
  {"input": [[9, 9, 9, 9, 9, 9, 9], [9, 9, 9, 9]], "expected": [8, 9, 9, 9, 0, 0, 0, 1]}
]
```

### Hidden

```json
[
  {
    "input": [
      [
        1
      ],
      [
        9
      ]
    ],
    "expected": [
      0,
      1
    ]
  },
  {
    "input": [
      [
        9
      ],
      [
        1
      ]
    ],
    "expected": [
      0,
      1
    ]
  },
  {
    "input": [
      [
        5
      ],
      [
        5
      ]
    ],
    "expected": [
      0,
      1
    ]
  },
  {
    "input": [
      [
        0,
        1
      ],
      [
        0,
        9
      ]
    ],
    "expected": [
      0,
      0,
      1
    ]
  },
  {
    "input": [
      [
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9
      ],
      [
        1
      ]
    ],
    "expected": [
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      1
    ]
  },
  {
    "input": [
      [
        1,
        8,
        9
      ],
      [
        0
      ]
    ],
    "expected": [
      1,
      8,
      9
    ]
  },
  {
    "input": [
      [
        2,
        4,
        9
      ],
      [
        5,
        6,
        4,
        9
      ]
    ],
    "expected": [
      7,
      0,
      4,
      0,
      1
    ]
  },
  {
    "input": [
      [
        9,
        9,
        9,
        9,
        9,
        9,
        9
      ],
      [
        9,
        9,
        9,
        9,
        9,
        9,
        9
      ]
    ],
    "expected": [
      8,
      9,
      9,
      9,
      9,
      9,
      9,
      1
    ]
  },
  {
    "input": [
      [
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1
      ],
      [
        9
      ]
    ],
    "expected": [
      0,
      1,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      1
    ]
  },
  {
    "input": [
      [
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9,
        9
      ],
      [
        1
      ]
    ],
    "expected": [
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      1
    ]
  },
  {
    "input": [
      [
        7,
        8,
        9,
        1,
        2,
        3,
        4,
        5
      ],
      [
        6,
        5,
        4,
        3,
        2,
        1
      ]
    ],
    "expected": [
      3,
      4,
      4,
      5,
      4,
      4,
      4,
      5
    ]
  },
  {
    "input": [
      [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9
      ],
      [
        9,
        8,
        7,
        6,
        5,
        4,
        3,
        2,
        1
      ]
    ],
    "expected": [
      0,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1,
      1
    ]
  }
]
```
