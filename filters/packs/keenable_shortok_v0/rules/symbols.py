'''
Define related symbols
'''

import re

#####################
# Bullet Points  
#####################

# # Bullet points in Dolma:
# BULLET_POINTS = ("*", "-")

# # Bullet points in RedPajama V2
# BULLET_POINT_SYMBOLS = (
#     "\u2022",  # bullet point
#     "\u2023",  # triangular bullet point
#     "\u25B6",  # black right pointing triangle
#     "\u25C0",  # black left pointing triangle
#     "\u25E6",  # white bullet point
#     "\u25A0",  # black square
#     "\u25A1",  # white square
#     "\u25AA",  # black small square
#     "\u25AB",  # white small square
#     "\u2013",  # en dash
# )

# Our Modified Bullet points
BULLET_POINT_SYMBOLS = (
    "\u2022",  # • bullet point
    "\u2023",  # ‣ triangular bullet point
    "\u25B6",  # ▶ black right pointing triangle
    "\u25C0",  # ◀ black left pointing triangle
    "\u25E6",  # ◦ white bullet point
    "\u25A0",  # ■ black square
    "\u25A1",  # □ white square
    "\u25AA",  # ▪ black small square
    "\u25AB",  # ▫ white small square
    "\u002d",  # - en dash
    "\u2013",  # – dash
    "\u2014",  # — zh dash 
    "\u002a",  # * star
)
#####################
# Ellipsis Symbols
#####################

# # Ellipsis Symbols in Dolma: 
# "\u2026"

# # Ellipsis Symbols in RedPajama V2
# ELLIPSIS_SYMBOLS = ("...", "…")

# Our Modified Ellipsis Symbols
ELLIPSIS_SYMBOLS = ("...", "…", "[...]", "[…]")


#####################
# Stop Words
#####################

# # Stop words in Dolma:
# REQUIRED_ENGLISH_WORDS = {"the", "be", "to", "of", "and", "that", "have", "with"}

# # Stop words in RedPajama V2:
# A long language-specific stop words list from RedPajama-Data-V2/app/src/core/quality_signals/utils/stop_words.py

# Original description from Gopher: 
# remove documents that do not contain at least two of the following English words: the, be, to, of, and, that, have, with
# Our Choice:
STOP_WORDS = {"the", "be", "to", "of", "and", "that", "have", "with"}


#####################
# Symbol-Word ratio
#####################
# # Symbols used for symbol-word ratio
# SYMBOLS = {"#", "\u2026"}  # Dolma
# SYMBOLS = ("#", "...", "…")  # RedPajama V2
SYMBOLS = ("#", "...", "…")  # ours


#####################
# Alphabetic Words
#####################

# # Dolma
# character.isalpha()

# # RedPajama
# ALPH_REGEX = re.compile(r"[a-zA-Z]")

# Our choice
# character.isalpha() could match non-English characters
ALPH_REGEX = re.compile(r"[a-zA-Z]")


SENT_PATTERN = re.compile(r'\b[^.!?]+[.!?]*', flags=re.UNICODE)