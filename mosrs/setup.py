#!/usr/bin/env python2
"""
Copyright 2016 ARC Centre of Excellence for Climate Systems Science

author: Scott Wales <scott.wales@unimelb.edu.au>

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import print_function
import argparse
from subprocess import Popen, PIPE
from textwrap import dedent
from os import environ, rename, path
from shutil import copy2

from mosrs.host import get_host, on_accessdev
from mosrs.message import info, warning, todo
from . import auth, gpg, message

class SetupError(Exception):
    """
    Indicates user needs to take action before setup can complete
    """
    pass

def prompt_or_default(prompt, default):
    """
    Ask a question with a default answer

    Returns: answer or default
    """
    response = raw_input('{} [{}]: '.format(prompt, default)).strip()
    if response == '':
        response = default
    return response

def check_rose():
    """
    Check the rose command
    """
    try:
        auth.check_rose()
    except auth.AuthError as exc:
        raise SetupError(*(exc.args))

def gpg_startup():
    """
    Insert or append a GPG agent script into the user's startup script
    """
    gpg_agent_script = dedent("""
    # mosrs-setup gpg_agent_script: DO NOT EDIT BETWEEN HERE AND END
    function export_gpg_environ {
        export GPG_TTY=$(tty)
        export GPG_AGENT_INFO="$(gpgconf --list-dirs agent-socket):0:1"
    }
    function start_gpg_agent {
        mkdir -p $HOME/.gnupg
        gpg-connect-agent /bye
        export_gpg_environ
    }
    if in_interactive_shell; then
        if in_login_shell; then
            start_gpg_agent
        fi
    fi
    # mosrs-setup gpg_agent_script: END

    """)
    home = environ['HOME']
    startup_name = '.bashrc'
    startup_path = path.join(home, startup_name)
    if not path.exists(startup_path):
        warning('Startup script ~/{} does not exist.'.format(startup_name))
        todo('Please contact the helpdesk.')
        raise SetupError
    else:
        # Check if gpg_agent_script is already referenced
        grep_gpg_agent_script = Popen(
            ['grep', 'mosrs-setup gpg_agent_script', startup_path],
            stdout=PIPE)
        grep_gpg_agent_script.communicate()
        if grep_gpg_agent_script.returncode == 0:
            return

        # Old filename and pathname used for rename or copy
        old_name = startup_name + '.old'
        old_path = path.join(home, old_name)
        # Look for NCI boilerplate in startup file
        boilerplate = 'if in_interactive_shell; then'
        grep_boilerplate = Popen(
            ['grep', boilerplate, startup_path],
            stdout=PIPE)
        grep_boilerplate.communicate()
        if grep_boilerplate.returncode == 0:
            # Boilerplate has been found
            rename(startup_path, old_path)
            # Insert gpg_agent_script
            with open(old_path, 'r') as old_startup_file:
                old = old_startup_file.read()
                insert_here = old.find(boilerplate)
                new = old[:insert_here] + gpg_agent_script + old[insert_here:]
                with open(startup_path, 'w') as startup_file:
                    startup_file.write(new)
        else:
            copy2(startup_path, old_path)
            # Append gpg_agent_script
            with open(startup_path, 'a') as startup_file:
                startup_file.write(gpg_agent_script)

    todo(dedent(
        """
        GPG Agent has been added to your startup script. Please log out of {}
        then back in again to make sure it has been activated.
        """.format(get_host())
        ))
    raise SetupError

def setup_mosrs_account():
    """
    Setup MOSRS
    """
    try:
        gpg.start_gpg_agent()
    except gpg.GPGError as exc:
        warning('GPGError in setup_mosrs_account:')
        for arg in exc.args:
            info(arg)
        raise

    # Save account details and cache credentials
    mosrs_request = None
    while mosrs_request not in ['yes', 'no', 'y', 'n']:
        mosrs_request = prompt_or_default('Do you have a MOSRS account', 'yes')
        mosrs_request = mosrs_request.lower()
    if mosrs_request.startswith('y'):
        try:
            auth.check_or_update()
        except auth.AuthError:
            warning('Authentication check and update failed.')
            todo(dedent(
                """
                Please check your credentials. If you have recently reset your password
                it may take a bit of time for the server to recognise the new password.
                """))
            raise SetupError
    else:
        todo(dedent(
            """
            Please send a request for a MOSRS account to your MOSRS Group Sponsor,
            copying in the Lead Chief Investigator of your NCI project.
            See https://my.nci.org.au for information on your project.
            """))
        raise SetupError

def main():
    """
    The mosrs-setup console script
    """
    print()
    if on_accessdev():
        warning('This version of mosrs-setup is not intended to run on accessdev.')
        return

    parser = argparse.ArgumentParser(
        description='Set up MOSRS authentication for Rose and Subversion by storing credentials')
    parser.add_argument(
        '--debug',
        dest='debugging',
        action='store_true',
        help='enable printing of debug messages')
    args = parser.parse_args()

    if args.debugging:
        message.debugging = True

    print(
        'This script will set up your account to use Rose and the MOSRS Subversion repositories\n')

    try:
        check_rose()
        try:
            setup_mosrs_account()
        except gpg.GPGError:
            return
        except SetupError:
            raise

        # Insert or append a GPG agent script into the user's startup script
        gpg_startup()
    except SetupError:
        todo('Once this has been done please run this setup script again.')
    else:
        # Account successfully created
        info(dedent(
            """
            You are now able to use Rose and the MOSRS Subversion repositories.
            To see a list of available experiments run:

                rosie go

            Your password will be cached for a maximum of 12 hours.
            To store your password again run:

                mosrs-auth
            """))
    finally:
        info('You can ask for help with the ACCESS systems by emailing "help@nci.org.au".')

if __name__ == '__main__':
    main()
