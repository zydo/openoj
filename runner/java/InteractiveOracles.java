import java.util.ArrayList;
import java.util.List;

/**
 * Interactive oracles for hidden-API problems (type "interactive"), each
 * mirroring its python_harness.py counterpart exactly: wrap the case's
 * hidden state, charge a query budget, and report a judged outcome from
 * final state where the solution method returns void.
 */
public final class InteractiveOracles {

    private InteractiveOracles() {}

    /** 489 robot-room-cleaner: verdict = the exact set of cleaned cells. */
    public static final class Robot {
        private static final int[][] DIRECTIONS = {{-1, 0}, {0, 1}, {1, 0}, {0, -1}};
        private final int[][] room;
        private final int rows;
        private final int cols;
        private int row;
        private int col;
        private int face; // starts facing up, LeetCode convention
        private final java.util.TreeSet<long[]> cleaned = new java.util.TreeSet<>(
            (a, b) -> a[0] != b[0] ? Long.compare(a[0], b[0]) : Long.compare(a[1], b[1])
        );
        private long budget;

        public Robot(List<Object> roomData, int startRow, int startCol, long budget) {
            this.room = new int[roomData.size()][];
            for (int r = 0; r < roomData.size(); r++) {
                List<Object> rowValues = asRow(roomData.get(r), r);
                this.room[r] = new int[rowValues.size()];
                for (int c = 0; c < rowValues.size(); c++) {
                    this.room[r][c] = ((Number) rowValues.get(c)).intValue();
                }
            }
            this.rows = this.room.length;
            this.cols = this.rows == 0 ? 0 : this.room[0].length;
            this.row = startRow;
            this.col = startCol;
            this.budget = budget;
            clean();
        }

        private void spend() {
            if (budget <= 0) {
                throw new IllegalStateException("Robot operation budget exhausted");
            }
            budget -= 1;
        }

        public boolean move() {
            spend();
            int nr = row + DIRECTIONS[face][0];
            int nc = col + DIRECTIONS[face][1];
            if (nr < 0 || nr >= rows || nc < 0 || nc >= cols || room[nr][nc] == 0) {
                return false; // wall or obstacle: stays in place
            }
            row = nr;
            col = nc;
            return true;
        }

        public void turnLeft() {
            spend();
            face = (face + 3) % 4;
        }

        public void turnRight() {
            spend();
            face = (face + 1) % 4;
        }

        public void clean() {
            spend();
            cleaned.add(new long[] {row, col});
        }

        public Object verdict() {
            List<Object> cells = new ArrayList<>();
            for (long[] cell : cleaned) {
                List<Object> pair = new ArrayList<>();
                pair.add((int) cell[0]);
                pair.add((int) cell[1]);
                cells.add(pair);
            }
            return cells;
        }
    }

    /** 843 guess-the-word: secret must be found within the guess budget. */
    public static final class Master {
        private final String secret;
        private long budget;
        private boolean found;

        public Master(List<Object> wordlist, String secret, long budget) {
            this.secret = secret;
            this.budget = budget;
        }

        public int guess(String word) {
            if (budget <= 0) {
                throw new IllegalStateException("Master guess budget exhausted");
            }
            budget -= 1;
            if (word.equals(secret)) {
                found = true;
            }
            int matches = 0;
            for (int i = 0; i < Math.min(word.length(), secret.length()); i++) {
                if (word.charAt(i) == secret.charAt(i)) {
                    matches += 1;
                }
            }
            return matches;
        }

        public Object verdict() {
            return found;
        }
    }

    /** 1095 find-in-mountain-array: get(index) under a call budget. */
    public static final class MountainArray {
        private final int[] mountain;
        private long budget;

        public MountainArray(List<Object> values, long budget) {
            this.mountain = new int[values.size()];
            for (int i = 0; i < values.size(); i++) {
                this.mountain[i] = ((Number) values.get(i)).intValue();
            }
            this.budget = budget;
        }

        public int get(int index) {
            if (budget <= 0) {
                throw new IllegalStateException("MountainArray query budget exhausted");
            }
            budget -= 1;
            if (index < 0 || index >= mountain.length) {
                throw new ArrayIndexOutOfBoundsException("MountainArray index out of range");
            }
            return mountain[index];
        }

        public int length() {
            return mountain.length;
        }
    }

    /** 1428 leftmost-column-with-at-least-a-one: get + dimensions. */
    public static final class BinaryMatrix {
        private final int[][] matrix;
        private long budget;

        public BinaryMatrix(List<Object> rows, long budget) {
            this.matrix = new int[rows.size()][];
            for (int r = 0; r < rows.size(); r++) {
                List<Object> rowValues = asRow(rows.get(r), r);
                this.matrix[r] = new int[rowValues.size()];
                for (int c = 0; c < rowValues.size(); c++) {
                    this.matrix[r][c] = ((Number) rowValues.get(c)).intValue();
                }
            }
            this.budget = budget;
        }

        public int get(int row, int col) {
            if (budget <= 0) {
                throw new IllegalStateException("BinaryMatrix query budget exhausted");
            }
            budget -= 1;
            return matrix[row][col];
        }

        public List<Integer> dimensions() {
            return List.of(matrix.length, matrix.length == 0 ? 0 : matrix[0].length);
        }
    }

    /** 702 search-in-a-sorted-array-of-unknown-size: sentinel past the end. */
    public static final class ArrayReader {
        public static final int SENTINEL = Integer.MAX_VALUE;
        private final int[] arr;
        private long budget;

        public ArrayReader(List<Object> values, long budget) {
            this.arr = new int[values.size()];
            for (int i = 0; i < values.size(); i++) {
                this.arr[i] = ((Number) values.get(i)).intValue();
            }
            this.budget = budget;
        }

        public int get(int index) {
            if (budget <= 0) {
                throw new IllegalStateException("ArrayReader query budget exhausted");
            }
            budget -= 1;
            return index >= 0 && index < arr.length ? arr[index] : SENTINEL;
        }
    }

    /** 3023 find-pattern-in-infinite-stream-i: next() yields bits in order. */
    public static final class InfiniteStream {
        private final int[] bits;
        private long budget;
        private int position;

        public InfiniteStream(List<Object> values, long budget) {
            this.bits = new int[values.size()];
            for (int i = 0; i < values.size(); i++) {
                this.bits[i] = ((Number) values.get(i)).intValue();
            }
            this.budget = budget;
        }

        public int next() {
            if (budget <= 0) {
                throw new IllegalStateException("InfiniteStream query budget exhausted");
            }
            budget -= 1;
            return bits[position++];
        }
    }

    private static List<Object> asRow(Object value, int index) {
        if (value instanceof List<?> list) {
            @SuppressWarnings("unchecked")
            List<Object> cast = (List<Object>) list;
            return cast;
        }
        throw new IllegalArgumentException("Row " + index + " must be a list");
    }
}
