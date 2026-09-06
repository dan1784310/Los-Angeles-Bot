# banned_words.py

# Words / phrases that should be blocked.
BANNED_WORDS = [
    "67",
    "six seven",
    "sex",
]

# These are allowed even though they contain "67".
# Example:
# 567 -> allowed
# 678 -> allowed
WHITELISTED_WORDS = [
    "567",
    "678",
]

# Discord USER IDs that completely bypass the banned-word system.
# Put the user's numeric Discord ID inside the list.
#
# Example:
# WHITELISTED_USERS = [
#     123456789012345678,
#     987654321098765432,
# ]
#
# Keep this empty if nobody should be exempt.
WHITELISTED_USERS = [
    1070969846508028007,
]
