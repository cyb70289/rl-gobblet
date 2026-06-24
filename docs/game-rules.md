# Gobblet — Game Rules

This document is the single source of truth for the Gobblet game rules.

## Goal

Be the first player to form a winning line (defined below) on the 3x3 board.

## Equipment

- A 3x3 board with 9 cells, arranged in 3 rows and 3 columns.
- Two players: **Red** and **Blue**.
- Each player has **6 pieces**: 2 Small (S), 2 Middle (M), 2 Large (L).
- Pieces are round buckets placed bottom-up in a cell. A larger bucket can cover
  a smaller bucket. Pieces are distinct entities (the two S pieces of a player are
  separate) but are interchangeable for win purposes.

## Stacking (covering) rules

A piece may be placed on top of another piece in a cell only if the placed piece is
**strictly larger** than the piece currently on top of that cell.

- Large may cover Middle or Small (any color).
- Middle may cover Small (any color).
- Small may not cover anything (it can only go on an empty cell).
- Equal sizes may not cover each other.
- A larger piece may not be covered by a smaller piece.
- Covering is allowed over your own or your opponent's pieces.

Each cell is therefore a **stack** ordered from smallest (bottom) to largest (top),
with strictly increasing sizes from bottom to top. Only the **top piece** of a cell
is considered "on top" for win detection and for being movable.

## Turn order

- Red moves first.
- Players alternate, one action per turn.
- A turn always consists of exactly one action: either a **Place** or a **Move**
  (see below). There is no pass.

## Actions

### Place

Take one of your pieces from your tray (unplaced pieces) and put it on a board cell.

Allowed destination:
- An empty cell, OR
- A cell whose top piece is strictly smaller than the piece being placed.

### Move

Take one of your own pieces that is currently the top piece of its cell and relocate
it to another board cell.

Allowed source: any cell whose top piece belongs to you.
Allowed destination:
- A different cell than the source (moving back to the source cell is a no-op and
  is **not allowed**), AND
- Either empty, OR has a top piece strictly smaller than the moved piece.

A moved piece stays on the board; it does **not** return to the tray. Moving is
allowed at any time, even if the player still has unplaced pieces in the tray.

You may only move **your own** top pieces. You may never move an opponent's piece.

## Winning

A player wins when, after an action, there exist three of that player's pieces,
all at the top of their cells, all the same color, occupying a complete line
(row, column, or diagonal), and the sizes along that line are in **strict
monotonic order** — either Small → Middle → Large or Large → Middle → Small
(positionally along the line).

Either direction is allowed per line. Concretely the 8 lines are:
- Rows 0, 1, 2 (each read left→right as S-M-L, or right→left as S-M-L)
- Columns 0, 1, 2 (each read top→bottom as S-M-L, or bottom→top as S-M-L)
- The two diagonals (each read start→end as S-M-L, or end→start as S-M-L)

That gives 16 winning size/position patterns total.

Only the top piece of each cell participates in win detection. Covered (non-top)
pieces do not count toward a winning line.

## Resolving the board after an action

After every action (Place or Move), the board is evaluated for winning lines for
**both** players:

1. If only the acting player has a winning line → the acting player wins.
2. If only the opponent has a winning line → the opponent wins.
   (This can happen after a Move that uncovers an opponent's piece, completing
   the opponent's line.)
3. If **both** players simultaneously have a winning line → the **opponent**
   (the non-acting player) wins. This is the "both may win" rule from the
   original plan.
4. If neither player has a winning line → play continues; the turn passes to
   the other player.

Notes:
- A Place can only create a winning line for the acting player, because the
  placed piece is the acting player's color and covering only removes an
  opponent's top piece (breaking, not completing, any opponent line). So the
  "both may win" case can only arise from a Move.
- A Move can create the acting player's winning line (by completing a line
  with the moved piece) and can simultaneously uncover an opponent's winning
  line (by removing a top piece that was hiding an opponent's piece beneath).
  When both occur, the opponent wins per rule 3 above.

## Game end

- The game ends as soon as a winner is determined per the rules above.
- There is no automatic draw / repetition detection in the manual web page.
  Players may self-judge a draw and press Restart at any time.
- The board is locked once a winner is declared; no further actions are allowed
  until a Restart.

## Summary of invariants

- 12 pieces total: 6 Red (2S, 2M, 2L) and 6 Blue (2S, 2M, 2L).
- Each cell's stack is strictly increasing in size from bottom to top.
- Only top pieces are movable (and only your own).
- Only top pieces count toward winning lines.
- A moved piece stays on the board; only unplaced pieces live in the tray.
- Win = three same-color tops in a line with sizes strictly monotonic
  (S-M-L or L-M-S) along the line.
