import re

from toffee import Bundle


def __gen_bundle_code(bundle_name: str, signals, max_width: int):
    """
    Generates bundle code using a list of signals.

    Args:
        bundle_name: The name of the bundle.
        signals: The list of signals.
        max_width: The maximum width of the line.

    Returns:
        The bundle code.
    """

    signals_num = len(signals)

    if signals_num == 0:
        end_code = f" = Signal()"
    else:
        end_code = f" = Signals({signals_num})"

    code = f"from toffee import Bundle\nfrom toffee import Signals, Signal\n\nclass {bundle_name}(Bundle):\n"
    code_line = "\t"
    index = 0

    TAB_SIZE = 4
    while index < signals_num:
        code_line = "\t"

        code_line += f"{signals[index]}, "
        current_width = TAB_SIZE + len(signals[index]) + 2 + 1
        index += 1

        while (
            index < signals_num and current_width + len(signals[index]) + 2 <= max_width
        ):
            code_line += f"{signals[index]}, "
            current_width += len(signals[index]) + 2
            index += 1

        if index == signals_num:
            code_line = code_line[:-2]
            current_width -= 3

            if current_width + len(end_code) <= max_width:
                code_line += end_code + "\n"
            else:
                code_line += " \\\n\t" + end_code[1:] + "\n"
        else:
            code_line += "\\\n"

        code += code_line

    return code


def gen_bundle_code_from_prefix(
    bundle_name: str, dut, prefix: str = "", max_width: int = 120
):
    """
    Generates a bundle using all the signals with the specified prefix.

    Args:
        bundle_name: The name of the bundle.
        dut: The DUT.
        prefix: The prefix of the signals.
        max_width: The maximum width of the line.

    Returns:
        The bundle code.
    """

    signals = []

    for dict in Bundle.dut_all_signals(dut):
        name = dict["name"]
        if name.startswith(prefix):
            signals.append(name[len(prefix) :])

    signals.sort()
    signals_num = len(signals)
    assert signals_num > 0, f"No signals found with prefix {prefix}"

    code = __gen_bundle_code(bundle_name, signals, max_width)
    code += "\n"
    code += f'bundle = {bundle_name}.from_prefix("{prefix}")\n'

    return code


def gen_bundle_code_from_regex(bundle_name: str, dut, regex: str, max_width: int = 120):
    """
    Generates a bundle using all the signals that match the specified regex.

    Args:
        bundle_name: The name of the bundle.
        dut: The DUT.
        regex: The regex of the signals.
        max_width: The maximum width of the line.

    Returns:
        The bundle code.
    """

    signals = []

    for dict in Bundle.dut_all_signals(dut):
        name = dict["name"]
        match = re.search(regex, name)

        if match is not None:
            groups = ["" if x is None else x for x in match.groups()]
            name = "".join(groups)
            signals.append(name)

    signals.sort()
    signals_num = len(signals)
    assert signals_num > 0, f"No signals found with regex {regex}"

    code = __gen_bundle_code(bundle_name, signals, max_width)
    code += "\n"
    code += f'bundle = {bundle_name}.from_regex(r"{regex}")\n'

    return code


def gen_bundle_code_from_dict(bundle_name: str, dut, dict: dict, max_width: int = 120):
    """
    Generates a bundle using a dictionary.

    Args:
        bundle_name: The name of the bundle.
        dut: The DUT.
        dict: The dictionary of signals.
        max_width: The maximum width of the line.

    Returns:
        The bundle code.
    """

    signals = []

    dut_signals = [signal["name"] for signal in Bundle.dut_all_signals(dut)]
    for key, value in dict.items():
        if value in dut_signals:
            signals.append(key)

    signals.sort()
    signals_num = len(signals)
    assert signals_num > 0, f"No signals found in the dictionary"

    code = __gen_bundle_code(bundle_name, signals, max_width)
    code += "\n"
    code += f"bundle = {bundle_name}.from_dict({dict})\n"

    return code
