"""Fixed vocabularies for the lifting log. docs/schema.md explains each field."""

MUSCLES = [
    "quads", "hamstrings", "glutes", "adductors", "calves",
    "chest", "front-delts", "side-delts", "rear-delts",
    "lats", "upper-back", "traps",
    "biceps", "triceps", "forearms",
    "abs", "spinal-erectors",
]

EQUIPMENT = ["barbell", "dumbbell", "kettlebell", "machine", "cable", "bodyweight", "band", "other"]

# How a segment's load number is read.
#   total       whole weight moved (barbell including the bar, plate-loaded total)
#   per-hand    weight in each hand (dumbbells, kettlebells)
#   bodyweight  added (+) or assisting (-) weight on top of bodyweight x share
#   machine     the weight the machine shows or is loaded with
LOAD_TYPES = ["total", "per-hand", "bodyweight", "machine"]

MEASURES = ["reps", "hold"]  # hold = timed, segments carry seconds instead of reps

SET_TYPES = ["warm-up", "regular", "failure", "drop", "myo-rep", "myo-match"]
PR_SET_TYPES = ["regular", "failure"]          # only these feed PRs and e1RM
BEST_SET_TYPES = ["drop", "myo-rep", "myo-match"]  # these get best-set tracking

MODES = ["bilateral", "alternating", "one-side"]
SIDES = ["both", "left", "right"]
UNITS = ["kg", "lb"]

LB_PER_KG = 2.2046226218

# Every timestamp the log writes (logged_at, stats.json's generated) is stamped in this
# zone, whatever machine runs the code, so it lines up with the session's date and times.
TIMEZONE = "America/Los_Angeles"

# e1RM rules
E1RM_MAX_REPS = 12   # sets with more full reps than this are left out
E1RM_MAX_RIR = 4     # sets easier than RPE 6 (RIR above 4) are left out

# Weekly volume: credit a set gives each muscle
PRIMARY_CREDIT = 1.0
SECONDARY_CREDIT = 0.5
