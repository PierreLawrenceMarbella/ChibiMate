"""Editable dialogue and timing for local character reactions."""

DIALOGUE = {
    "happy": ("Hehe~!", "I'm happy to see you!", "Yay!"),
    "surprised": ("Eh?!", "You surprised me!", "W-What?!"),
    "shy": ("Hmph!", "I-It's not like I was waiting!", "Don't stare at me!"),
    "idle": ("What are you doing?", "I'm getting bored...", "Let's take a little break!"),
}
CLICK_REACTIONS = ("happy", "surprised", "shy")
RANDOM_REACTION_SECONDS = (20.0, 45.0)
REACTION_SECONDS = (1.5, 2.0)
BUBBLE_MILLISECONDS = 3000
