import java.util.List;
import java.util.Map;

/**
 * Interactive oracle for hidden-grid problems (type "interactive"). Solutions
 * explore a grid they cannot see through this API; the judge constructs it
 * from the case data (grid costs, start, target) and enforces a query budget.
 *
 * Mirrors runner/python_harness.py's GridMaster exactly.
 */
public final class GridMaster {

    private static final String U = "U";
    private static final String D = "D";
    private static final String L = "L";
    private static final String R = "R";

    private final int[][] cost;
    private final int rows;
    private final int cols;
    private final int targetRow;
    private final int targetCol;
    private long budget;
    private int row;
    private int col;

    public GridMaster(List<Object> gridData, int startRow, int startCol, int targetRow, int targetCol, long budget) {
        this.cost = new int[gridData.size()][];
        for (int r = 0; r < gridData.size(); r++) {
            List<Object> rowValues = asRow(gridData.get(r), r);
            this.cost[r] = new int[rowValues.size()];
            for (int c = 0; c < rowValues.size(); c++) {
                Object value = rowValues.get(c);
                if (!(value instanceof Number number)) {
                    throw new IllegalArgumentException("Grid cells must be numbers");
                }
                this.cost[r][c] = number.intValue();
            }
        }
        this.rows = this.cost.length;
        this.cols = this.rows == 0 ? 0 : this.cost[0].length;
        this.row = startRow;
        this.col = startCol;
        this.targetRow = targetRow;
        this.targetCol = targetCol;
        this.budget = budget;
    }

    private static List<Object> asRow(Object value, int index) {
        if (value instanceof List<?> list) {
            @SuppressWarnings("unchecked")
            List<Object> cast = (List<Object>) list;
            return cast;
        }
        throw new IllegalArgumentException("Grid row " + index + " must be a list");
    }

    private void spend() {
        if (budget <= 0) {
            throw new IllegalStateException("GridMaster query budget exhausted");
        }
        budget -= 1;
    }

    private int[] delta(String direction) {
        switch (direction) {
            case U: return new int[] {-1, 0};
            case D: return new int[] {1, 0};
            case L: return new int[] {0, -1};
            case R: return new int[] {0, 1};
            default: throw new IllegalArgumentException("Direction must be one of U, D, L, R");
        }
    }

    private boolean enterable(int r, int c) {
        return r >= 0 && r < rows && c >= 0 && c < cols && cost[r][c] > 0;
    }

    public boolean canMove(char direction) {
        return canMove(String.valueOf(direction));
    }

    public boolean canMove(String direction) {
        spend();
        int[] step = delta(direction);
        return enterable(row + step[0], col + step[1]);
    }

    public int move(char direction) {
        return move(String.valueOf(direction));
    }

    public int move(String direction) {
        spend();
        int[] step = delta(direction);
        int nextRow = row + step[0];
        int nextCol = col + step[1];
        if (!enterable(nextRow, nextCol)) {
            return -1;
        }
        row = nextRow;
        col = nextCol;
        return cost[row][col];
    }

    public boolean isTarget() {
        spend();
        return row == targetRow && col == targetCol;
    }
}
