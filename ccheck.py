import os
import sys
import clang.cindex
from loguru import logger

LIBDIR = '/opt/homebrew/Cellar/llvm/19.1.4/lib/'

logger.remove()  # Remove the default logger
logger.add(sys.stderr, level='DEBUG',
           format="<dim>{function}:{line}</dim>  {message}")

UNSAFE_FUNCTIONS = ["atoi", "atof", "atol", "sprintf", "strtok", "gets", "strcpy", "strcat"]

def generate_ast_from_c(file_path: str):
    # Initialize Clang library with the path to libclang.
    # Update this path according to your system
    clang.cindex.Config.set_library_path(LIBDIR)

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file '{file_path}' does not exist.")

    index = clang.cindex.Index.create()
    translation_unit = index.parse(file_path)

    if not translation_unit:
        raise RuntimeError("Failed to create translation unit from file.")

    return translation_unit.cursor


def print_ast(cursor, indent=0):
    print('  ' * indent +
          f'{cursor.kind} {cursor.spelling} {cursor.displayname}')
    for child in cursor.get_children():
        print_ast(child, indent + 1)


def print_single_character_names(cursor):
    count = 0
    if cursor.kind.is_declaration() and len(cursor.spelling) == 1:
        print(f"Name: {cursor.spelling}, Line: {cursor.location.line}")
        count = 1
    for child in cursor.get_children():
        count += print_single_character_names(child)
    return count


def print_non_global_capitalized_variables(cursor):
    count = 0
    if cursor.kind == clang.cindex.CursorKind.VAR_DECL and cursor.spelling and cursor.spelling[0].isupper():
        if cursor.linkage != clang.cindex.LinkageKind.EXTERNAL:
            print(
                f"Non-global capitalized variable: {cursor.spelling}, Line: {cursor.location.line}")
            count = 1
    for child in cursor.get_children():
        count = count + \
            print_non_global_capitalized_variables(child)
    return count


def detect_argv_access_before_argc_check(cursor):
    argc_checked = False
    if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL:
        for child in cursor.get_children():
            if child.kind == clang.cindex.CursorKind.PARM_DECL and child.spelling == "argc":
                argc_checked = True
            if child.kind == clang.cindex.CursorKind.DECL_REF_EXPR and child.spelling == "argv":
                if not argc_checked:
                    print(f"Warning: 'argv' accessed before 'argc' check, Line: {
                          child.location.line}")
            if child.kind == clang.cindex.CursorKind.IF_STMT:
                argc_checked = True
        for child in cursor.get_children():
            argc_checked = argc_checked or detect_argv_access_before_argc_check(
                child)
    return argc_checked


def count_and_print_numeric_constants(cursor):
    count = 0
    if cursor.kind == clang.cindex.CursorKind.INTEGER_LITERAL:
        try:
            token = next(cursor.get_tokens())
            value = int(token.spelling)
            # Exclude numeric indexes into the argv array
            if value not in (0, 1, 2):
                line_number = cursor.location.line
                source_file = cursor.location.file
                if source_file is not None:
                    with open(source_file.name, 'r') as file:
                        lines = file.readlines()
                        code = lines[line_number - 1].strip()
                        if 'argv' not in code:
                            print(f"Numeric constant: {value}, Line: {
                                  line_number}, Code: '{lines[line_number - 1].strip()}'")
                            count += 1
        except StopIteration:
            pass
    for child in cursor.get_children():
        count += count_and_print_numeric_constants(child)
    return count

def detect_unsafe_functions(cursor):
    count = 0
    if cursor.kind == clang.cindex.CursorKind.CALL_EXPR:
        if cursor.spelling in UNSAFE_FUNCTIONS:
            print(f"Unsafe function used: {cursor.spelling}, Line: {cursor.location.line}")
            count += 1
        # else:
        #     for child in cursor.get_children():
        #         if child.kind == clang.cindex.CursorKind.DECL_REF_EXPR and child.spelling in UNSAFE_FUNCTIONS:
        #             print(f"Unsafe function used: {child.spelling}, Line: {child.location.line}")
        #             count += 1
    for child in cursor.get_children():
        count += detect_unsafe_functions(child)
    return count

if __name__ == "__main__":
    c_file_path = sys.argv[1]
    try:
        ast_root = generate_ast_from_c(c_file_path)
        print_ast(ast_root)

        print("\nSingle-character variable or function names:")
        count = print_single_character_names(ast_root)
        print('Total:', count)

        print("\nNon-global capitalized variables:")
        count = print_non_global_capitalized_variables(ast_root)
        print('Total:', count)

        print("\nDetecting 'argv' access before 'argc' check:")
        any = detect_argv_access_before_argc_check(ast_root)
        print('Any found:', 'yes' if any else 'no')

        print("\n\nDetecting any numeric constants:")
        count = count_and_print_numeric_constants(ast_root)
        print('Total:', count)

        print("\nDetecting unsafe function usage:")
        unsafe_count = detect_unsafe_functions(ast_root)
        print(f"Total number of unsafe functions used: {unsafe_count}")

    except Exception as e:
        print(f"Error: {e}")
