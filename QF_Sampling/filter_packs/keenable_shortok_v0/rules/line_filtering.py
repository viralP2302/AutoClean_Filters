from symbols import *
from utils import *


def check_javascript(text):
    if "javascript" not in text:
        return False
    if "enable" in text:
        return True
    if "disable" in text:
        return True
    if "require" in text:
        return True
    if "activate" in text:
        return True
    if "browser" in text:
        return True
    return False


def is_counter(input_text):
    pattern = r'^\d+\s+likes$'
    return bool(re.match(pattern, input_text))


# def line_filtering(line, attrs, line_idx, lines_count, new_lines, automaton):
def line_filtering(line, attrs, line_idx, lines_count, automaton):

    # Normalize the line text
    line_norm = line.strip().lower()
    word_cnt_line = len(line_norm.split())

    # 1.1 Remove lines not ending up in a terminal punctuation mark
    # if not line_norm.endswith((".", "?", "!", '"')):  # Done: Check if we need to use this
    #     return False, "C4_not_ending_with_terminal_punctuation"

    # 1.2 Remove lines containing word "javascript"
    # if "javascript" in line_norm:  # Done: refine the strategy
    if check_javascript(line_norm):
        return True  #, "1.2_C4_javascript"
    
    # Set the default for fraction_of_words_corrected_in_lines
    # Do not include the characters corrected by javascript into the counting
    attrs.fraction_of_words_corrected_in_lines += word_cnt_line

    # 1.3.1 Remove lines of uppercase characters only
    if line.isupper():
        return True  #, "1.3.1_RefinedWeb_uppercase_only"
    # 1.3.2 Remove lines of numerical characters
    if line_norm.isdigit():
        return True  #, "1.3.2_RefinedWeb_digits_only"
    # 1.3.3 Remove lines of counter
    if is_counter(line_norm):
        return True  #, "1.3.3_RefinedWeb_is_counter"
    # 1.3.4 Remove lines with only a few word
    if word_cnt_line <= 1:  # TODO: decide the threshold
        return True  #, "1.3.4_RefinedWeb_line_too_short"
    # Done: Decide whether to use 1.3.5 (Edit the line if it is short (≤ 10 words) and matches a pattern)

    # 2.2.1 Calculate the number of words that are corrected by above rules
    attrs.fraction_of_words_corrected_in_lines -= word_cnt_line

    # TODO: Remove toxic lines
    line_to_check = " "+line_norm+" "
    
    # # if contains_bad_word(automaton, line_to_check):
    # if j < 3 or j >= lines_count - 3:
    #     # if i == 1:
    #     #     print(j)
    #     #     print(line_to_check)
    #     if contains_bad_word(automaton, line_to_check) and len(line_norm.split()) < 10:
    #         ids_toxic[i].append(j)
    #         continue
    # bad_word_num = get_bad_word_num(automaton, line_to_check)
    # if bad_word_num/len(line_norm.split()) > 0.1:
    #     ids_toxic[i].append(j)
    #     continue
    bad_word_num = get_bad_word_num(automaton, line_to_check)
    if bad_word_num:
        # if the line is in the beginning or end of the document, remove this line
        if (line_idx < 3 or line_idx >= lines_count - 3) and len(line_norm.split()) < 10:
            return True  #, "1.4.1_Ours_toxic_line"
        # else: compute the number of bad words
        attrs.num_of_toxic_words += bad_word_num
        attrs.num_of_lines_with_toxic_words += 1

    # # Add the line to the new_line if it passed all above line-level filtering
    # new_lines.append(line)

    ## 2. Compute line-wise signal for later document-level removal
    # 2.2.2 Calculate the number of lines ending with an ellipsis
    if line.rstrip().endswith(ELLIPSIS_SYMBOLS):
        attrs.fraction_of_lines_ending_with_ellipsis += 1
    # 2.2.3 Calculate the number of lines starting with a bullet point
    if line.lstrip().startswith(BULLET_POINT_SYMBOLS):
        attrs.fraction_of_lines_starting_with_bullet_point += 1
    
    return False  #, None