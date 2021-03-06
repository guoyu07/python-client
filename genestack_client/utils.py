# -*- coding: utf-8 -*-

#
# Copyright (c) 2011-2015 Genestack Limited
# All Rights Reserved
# THIS IS UNPUBLISHED PROPRIETARY SOURCE CODE OF GENESTACK LIMITED
# The copyright notice above does not evidence any
# actual or intended publication of such source code.
#

import argparse
import sys


def isatty():
    """
    Return True if the file is connected to a tty device.

    :return: is a tty
    :rtype: bool
    """
    try:
        return sys.stdout.isatty()
    except AttributeError:
        return False


def make_connection_parser(user=None, password=None, host=None):
    """
    Creates an argument parser with the provided connection parameters.
    If one of `email`, `password` or `user` is specified, they are used. Otherwise, the default
    identity from the local config file will be used.

    :param user: user alias or email
    :type user: str
    :param password: user password
    :type password: str
    :param host: host
    :type host: str
    :return: parser
    :rtype: :py:class:`~argparse.ArgumentParser`
    """
    parser = argparse.ArgumentParser()
    group = parser.add_argument_group('connection')
    group.add_argument('-H', '--host', default=host, help="server host", metavar='<host>')
    group.add_argument('-u', dest='user', metavar='<user>', default=user, help='user alias from settings or email')
    group.add_argument('-p', dest='pwd', default=password, metavar='<password>', help='user password')
    return parser


def get_user(args=None):
    """
    Returns the user corresponding to the provided arguments.
    If `args` is `None`, uses :attr:`make_connection_parser` to get arguments.

    :param args: result of commandline parse
    :type args: argparse.Namespace
    :return: user
    :rtype: :py:class:`~genestack_client.settings.User.User`
    """

    from settings import config, User

    if args is None:
        args = make_connection_parser().parse_args()

    alias = args.user
    if not args.host and not args.pwd:
        if not alias and config.default_user:
            return config.default_user
        if alias in config.users:
            return config.users[alias]
    return User(email=alias, host=args.host, password=args.pwd)


def get_connection(args=None):
    """
    This is the same as :py:func:`get_user` . :py:meth:`~genestack_client.settings.User.User.get_connection`
    Generally the fastest way to get an active connection.

    :param args: argument from :attr:`argparse.parse_args`
    :type args: argparse.Namespace
    :return: connection
    :rtype: :py:class:`~genestack_client.Connection.Connection`
    """
    user = get_user(args)
    return user.get_connection(interactive=True)
