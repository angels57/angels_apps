"""19.0.1.1.0 -> 19.0.1.2.0: the dotted background becomes the default.

Companies still on the old default (brand gradient) move to it; a plain or
image background was chosen on purpose and stays.
"""


def migrate(cr, version):
    cr.execute(
        "UPDATE res_company SET angels_home_background = 'dots' "
        "WHERE angels_home_background = 'gradient'"
    )
