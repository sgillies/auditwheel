import os
from os.path import isfile, exists, abspath, basename
from .policy import (load_policies, get_policy_name, get_priority_by_name,
                     POLICY_PRIORITY_HIGHEST)
from .tools import EnvironmentDefault
import logging

logger = logging.getLogger(__name__)


def configure_parser(sub_parsers):
    policy_names = [p['name'] for p in load_policies()]
    highest_policy = get_policy_name(POLICY_PRIORITY_HIGHEST)
    help = "Vendor in external shared library dependencies of a wheel."
    p = sub_parsers.add_parser("repair", help=help, description=help)
    p.add_argument("WHEEL_FILE", help="Path to wheel file.")
    p.add_argument(
        "--extra-lib-name-tag",
        dest="EXTRA_LIB_NAME_TAG",
        help="Extra, optional tag for copied library names",
        default=os.environ.get("AUDITWHEEL_EXTRA_LIB_NAME_TAG", None),
    )
    p.add_argument(
        "--plat",
        action=EnvironmentDefault,
        env='AUDITWHEEL_PLAT',
        dest='PLAT',
        help='Desired target platform. (default: "%s")' % highest_policy,
        choices=policy_names,
        default=highest_policy)
    p.add_argument('-L',
                   '--lib-sdir',
                   dest='LIB_SDIR',
                   help=('Subdirectory in packages to store copied libraries.'
                         ' (default: ".libs")'),
                   default='.libs')
    p.add_argument('-w',
                   '--wheel-dir',
                   dest='WHEEL_DIR',
                   type=abspath,
                   help=('Directory to store delocated wheels (default:'
                         ' "wheelhouse/")'),
                   default='wheelhouse/')
    p.add_argument('--no-update-tags',
                   dest='UPDATE_TAGS',
                   action='store_false',
                   help=('Do not update the wheel filename tags and WHEEL info'
                         ' to match the repaired platform tag.'),
                   default=True)
    p.set_defaults(func=execute)


def execute(args, p):
    import os
    from distutils.spawn import find_executable
    from .repair import repair_wheel
    from .wheel_abi import analyze_wheel_abi

    if not isfile(args.WHEEL_FILE):
        p.error('cannot access %s. No such file' % args.WHEEL_FILE)
    if find_executable('patchelf') is None:
        p.error('cannot find the \'patchelf\' tool, which is required')

    logger.info('Repairing %s', basename(args.WHEEL_FILE))

    if not exists(args.WHEEL_DIR):
        os.makedirs(args.WHEEL_DIR)

    wheel_abi = analyze_wheel_abi(args.WHEEL_FILE)
    reqd_tag = get_priority_by_name(args.PLAT)

    if reqd_tag > get_priority_by_name(wheel_abi.sym_tag):
        msg = ('cannot repair "%s" to "%s" ABI because of the presence '
               'of too-recent versioned symbols. You\'ll need to compile '
               'the wheel on an older toolchain.' %
               (args.WHEEL_FILE, args.PLAT))
        p.error(msg)

    if reqd_tag > get_priority_by_name(wheel_abi.ucs_tag):
        msg = ('cannot repair "%s" to "%s" ABI because it was compiled '
               'against a UCS2 build of Python. You\'ll need to compile '
               'the wheel against a wide-unicode build of Python.' %
               (args.WHEEL_FILE, args.PLAT))
        p.error(msg)

    out_wheel = repair_wheel(
        args.WHEEL_FILE,
        abi=args.PLAT,
        lib_sdir=args.LIB_SDIR,
        out_dir=args.WHEEL_DIR,
        update_tags=args.UPDATE_TAGS,
        extra_lib_name_tag=args.EXTRA_LIB_NAME_TAG,
    )

    if out_wheel is not None:
        analyzed_tag = analyze_wheel_abi(out_wheel).overall_tag
        if reqd_tag < get_priority_by_name(analyzed_tag):
            logger.info(
                (
                    "Wheel is eligible for a higher priority tag. "
                    "You requested %s but I have found this wheel is "
                    "eligible for %s."
                ),
                args.PLAT,
                analyzed_tag,
            )
            out_wheel = repair_wheel(
                args.WHEEL_FILE,
                abi=analyzed_tag,
                lib_sdir=args.LIB_SDIR,
                out_dir=args.WHEEL_DIR,
                update_tags=args.UPDATE_TAGS,
                extra_lib_name_tag=args.EXTRA_LIB_NAME_TAG,
            )

        logger.info("\nFixed-up wheel written to %s", out_wheel)
