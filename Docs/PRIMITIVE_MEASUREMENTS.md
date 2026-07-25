# PAE primitive measurement table

Tolerance: **6.0 cm**. All dimensions from `pae/contract.py`.

| id | kind | footprint (mod) | size_cm (X x Y x Z) | aabb_min | origin | centered | ok |
|---|---|---|---|---|---|---|---|
| `wall_plain` | wall | 1x1 | 60.0x400.0x350.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `wall_window` | wall | 1x1 | 60.0x400.0x350.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `wall_arrowslit` | wall | 1x1 | 60.0x400.0x350.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `wall_door` | wall | 1x1 | 60.0x400.0x350.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `wall_arcade` | wall | 1x1 | 60.0x400.0x350.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `floor` | floor | 1x1 | 400.0x400.0x30.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `floor_hole` | floor | 1x1 | 400.0x400.0x30.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `stair_straight` | stair | 2x1 | 800.0x400.0x350.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `stair_spiral_quarter` | stair | 1x1 | 400.0x400.0x87.5 | (0.0,0.0,0.0) | center | True | yes |
| `tower_arc_quarter` | tower_arc | 1x1 | 400.0x400.0x350.0 | (0.0,0.0,0.0) | center | True | yes |
| `tower_crown` | tower_crown | 2x2 | 800.0x800.0x70.0 | (-400.0,-400.0,0.0) | center | True | yes |
| `tower_cap` | tower_cap | 2x2 | 800.0x800.0x297.5 | (-400.0,-400.0,0.0) | center | True | yes |
| `battlement` | battlement | 1x1 | 60.0x400.0x77.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `roof_pitched_gable` | roof | 1x1 | 400.0x400.0x240.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `roof_flat` | roof | 1x1 | 400.0x400.0x30.0 | (0.0,0.0,0.0) | min_corner | False | yes |
| `ground_plinth` | plinth | 1x1 | 400.0x400.0x30.0 | (0.0,0.0,0.0) | min_corner | False | yes |

All pieces within tolerance.
