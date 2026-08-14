# 1. Two Sum

## Metadata

```json
{
  "schema_version": 1,
  "slug": "two-sum",
  "difficulty": "Easy",
  "tags": ["Array", "Hash Table"],
  "source": {
    "label": "LeetCode — Two Sum",
    "url": "https://leetcode.com/problems/two-sum/description/"
  }
}
```

## Description

Given an array of integers `nums` and an integer `target`, return the indices
of the two numbers whose values add up to `target`.

You may assume that every input has **exactly one solution**, and you may not
use the same element twice.

You can return the answer in any order.

### Example 1

```text
Input: nums = [2,7,11,15], target = 9
Output: [0,1]
Explanation: nums[0] + nums[1] is 9, so return [0,1].
```

### Example 2

```text
Input: nums = [3,2,4], target = 6
Output: [1,2]
```

### Example 3

```text
Input: nums = [3,3], target = 6
Output: [0,1]
```

### Constraints

- `2 <= nums.length <= 10⁴`
- `-10⁹ <= nums[i] <= 10⁹`
- `-10⁹ <= target <= 10⁹`
- Only one valid answer exists.

### Follow-up

Can you design an algorithm with less than `O(n²)` time complexity?

## Hints

```json
[
  "A brute-force search considers every pair. Use it to identify the repeated work you could avoid.",
  "For a fixed value x, the number you need is target - x. What structure can locate that complement quickly?",
  "A hash map can remember values you have already visited and the index where each appeared."
]
```

## Invocation

```json
{
  "type": "function",
  "class_name": "Solution",
  "method": "twoSum",
  "parameters": [
    {
      "name": "nums",
      "codec": "json",
      "value_type": {
        "kind": "array",
        "items": {"kind": "integer", "bits": 32}
      }
    },
    {
      "name": "target",
      "codec": "json",
      "value_type": {"kind": "integer", "bits": 32}
    }
  ],
  "return_codec": "json",
  "return_type": {
    "kind": "array",
    "items": {"kind": "integer", "bits": 32}
  },
  "entrypoints": {
    "go": "twoSum",
    "rust": "two_sum",
    "typescript": "twoSum"
  },
  "comparison": "sorted"
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
from typing import List


class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        raise NotImplementedError("TODO")
```

### javascript

```javascript
/**
 * @param {number[]} nums
 * @param {number} target
 * @return {number[]}
 */
var twoSum = function(nums, target) {
    throw new Error("TODO");
};
```

### typescript

```typescript
function twoSum(nums: number[], target: number): number[] {
    throw new Error("TODO");
}
```

### java

```java
class Solution {
    public int[] twoSum(int[] nums, int target) {
        throw new UnsupportedOperationException("TODO");
    }
}
```

### cpp

```cpp
class Solution {
public:
    vector<int> twoSum(vector<int>& nums, int target) {
        throw logic_error("TODO");
    }
};
```

### go

```go
func twoSum(nums []int, target int) []int {
    panic("TODO")
}
```

### rust

```rust
impl Solution {
    pub fn two_sum(nums: Vec<i32>, target: i32) -> Vec<i32> {
        panic!("TODO")
    }
}
```

## Test Cases

### Public

```json
[
  {"input": [[2, 7, 11, 15], 9], "expected": [0, 1]},
  {"input": [[3, 2, 4], 6], "expected": [1, 2]},
  {"input": [[3, 3], 6], "expected": [0, 1]}
]
```

### Hidden

```json
[
  {"input": [[0, 4, 3, 0], 0], "expected": [0, 3]},
  {"input": [[-3, 4, 3, 90], 0], "expected": [0, 2]},
  {"input": [[-1, -2, -3, -4, -5], -8], "expected": [2, 4]},
  {"input": [[2, 5, 5, 11], 10], "expected": [1, 2]},
  {"input": [[12, -7, 4, 21, 9, 31], 43], "expected": [0, 5]},
  {"input": [[-1000000000, 7, 1000000000, 12], 0], "expected": [0, 2]},
  {"input": [[3, 2, 8, 4], 6], "expected": [1, 3]},
  {"input": [[0, 1, 2, -3, 5], -1], "expected": [2, 3]},
  {"input": [[-17, 24], 7], "expected": [0, 1]},
  {"input": [[8, 8, 8, 13, 8, -2], 11], "expected": [3, 5]},
  {"input": [[1, 4, 8, 15, 23, 42, 67, 91], 158], "expected": [6, 7]},
  {"input": [[18, -40, 11, -8, 27, 5], -29], "expected": [1, 2]},
  {"input": [[0, 19, -4, 6, 12], 19], "expected": [0, 1]},
  {"input": [[999999999, -999999998, 6, 14], 1], "expected": [0, 1]},
  {"input": [[14, 3, 29, -5, 72, 18], 13], "expected": [3, 5]}
]
```
