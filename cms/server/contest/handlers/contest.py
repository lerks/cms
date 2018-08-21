#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2016 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2017 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
# Copyright © 2015-2016 William Di Luigi <williamdiluigi@gmail.com>
# Copyright © 2016 Myungwoo Chun <mc.tamaki@gmail.com>
# Copyright © 2016 Amir Keivan Mohtashami <akmohtashami97@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Contest handler classes for CWS.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa
from six import iterkeys, iteritems

import ipaddress
import logging
from datetime import timedelta
from functools import wraps

from flask import g, request, redirect, abort, Blueprint, url_for, current_app, \
    render_template, after_this_request, session
from jinja2 import TemplateNotFound
from werkzeug.datastructures import LanguageAccept
from werkzeug.http import parse_accept_header

from cms import TOKEN_MODE_MIXED
from cms.db import Contest, Task, Submission, UserTest
from cms.locale import filter_language_codes, choose_language_code
from cms.server.contest.authentication import authenticate_request
from cmscommon.datetime import get_timezone

from ..phase_management import compute_actual_phase


logger = logging.getLogger(__name__)


NOTIFICATION_ERROR = "error"
NOTIFICATION_WARNING = "warning"
NOTIFICATION_SUCCESS = "success"


contest_bp = Blueprint('contest', 'cms.server.contest')


# @contest_bp.route('/<page>')
# def show(page):
#     try:
#         return render_template('pages/%s.html' % page)
#     except TemplateNotFound:
#         raise HTTPException(404)


@contest_bp.url_defaults
def add_contest_name(endpoint, values):
    # TODO This is fishy, we shouldn't need to check whethere contest is defined, it always is!
    if not hasattr(current_app, "contest_id") and hasattr(g, "contest"):
        values.setdefault('contest', g.contest.name)


@contest_bp.url_value_preprocessor
def pull_contest_name(endpoint, values):
    if not hasattr(current_app, "contest_id"):
        g.contest_name = values.pop("contest")


@contest_bp.before_request
def prepare_contest_for_contest():
    if hasattr(g, "contest_name"):
        g.contest = g.session.query(Contest).filter(
            Contest.name == g.contest_name).first()
        # TODO what if None?
        del g.contest_name
    elif hasattr(current_app, "contest_id"):
        Contest.get_from_id(current_app.contest_id, g.session)
    else:
        raise RuntimeError("cannot determine contest")

    if g.contest.allowed_localizations:
        lang_codes = filter_language_codes(
            list(iterkeys(g.available_translations)),
            g.contest.allowed_localizations)
        g.available_translations = dict(
            (k, v) for k, v in iteritems(g.available_translations)
            if k in lang_codes)

    g.phase = g.contest.phase(g.timestamp)

    cookie_name = g.contest.name + "_login"
    old_cookie = session.get(cookie_name, None)

    try:
        # In py2 Tornado gives us the IP address as a native binary
        # string, whereas ipaddress wants text (unicode) strings.
        # FIXME Still true with Flask?
        ip_address = ipaddress.ip_address(str(request.remote_addr))
    except ValueError:
        logger.warning("Invalid IP address provided by Flask: %s",
                       request.remote_addr)
        return None

    participation, new_cookie = authenticate_request(
        g.session, g.contest, g.timestamp, old_cookie, ip_address)

    if new_cookie is None:
        session.pop(cookie_name, None)
#    elif refresh_cookie:
    elif True:
        session[cookie_name] = new_cookie

    if participation is not None:
        g.participation = participation
        g.user = participation.user

        setup_locale()

        g.actual_phase, g.current_phase_begin, g.current_phase_end, g.valid_phase_begin, g.valid_phase_end = compute_actual_phase(
            g.timestamp, g.contest.start, g.contest.stop,
            g.contest.analysis_start if g.contest.analysis_enabled else None,
            g.contest.analysis_stop if g.contest.analysis_enabled else None,
            g.contest.per_user_time, g.participation.starting_time,
            g.participation.delay_time, g.participation.extra_time)

        if g.actual_phase == 0:
            g.phase = 0


def setup_locale():
    lang_codes = list(iterkeys(g.available_translations))

    browser_langs = parse_accept_header(
        request.headers.get("Accept-Language", ""),
        LanguageAccept).values()
    automatic_lang = choose_language_code(browser_langs, lang_codes)
    if automatic_lang is None:
        automatic_lang = lang_codes[0]
    g.automatic_translation = \
        g.available_translations[automatic_lang]

    cookie_lang = request.cookies.get("language", None)
    if cookie_lang is not None:
        chosen_lang = \
            choose_language_code([cookie_lang, automatic_lang],
                                 lang_codes)
        if chosen_lang == cookie_lang:
            g.cookie_translation = \
                g.available_translations[cookie_lang]
    else:
        chosen_lang = automatic_lang
    g.translation = g.available_translations[chosen_lang]

    g._ = g.translation.gettext
    g.n_ = g.translation.ngettext

    @after_this_request
    def set_header(response):
        response.headers["Content-Language"] = chosen_lang
        return response


def authentication_required(refresh_cookie=True):
    def decorator(f):
        @wraps(f)
        def wrapped_f(*args, **kwargs):
            if not hasattr(g, "participation"):
                # TODO make next relative?
                return redirect(url_for('contest.login', next=request.url))
            return f(*args, **kwargs)
        return wrapped_f
    return decorator


def actual_phase_required(*actual_phases):
    """Return decorator filtering out requests in the wrong phase.

    actual_phases ([int]): the phases in which the request can pass.

    return (function): the decorator.

    """
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if not hasattr(g, "participation") or (g.actual_phase not in actual_phases and not g.participation.unrestricted):
                # TODO maybe return some error code?
                return redirect(url_for("contest.main_handler"))
            else:
                return func(*args, **kwargs)
        return wrapped
    return decorator


@contest_bp.context_processor
def contest_render_params():
    ret = dict()

    ret["contest"] = g.contest

    ret["phase"] = g.phase

    ret["questions_enabled"] = g.contest.allow_questions
    ret["testing_enabled"] = g.contest.allow_user_tests

    if hasattr(g, "participation"):
        ret["participation"] = g.participation
        ret["user"] = g.user

        ret["actual_phase"] = g.actual_phase
        ret["current_phase_begin"] = g.current_phase_begin
        ret["current_phase_end"] = g.current_phase_end
        ret["valid_phase_begin"] = g.valid_phase_begin
        ret["valid_phase_end"] = g.valid_phase_end

        # set the timezone used to format timestamps
        ret["timezone"] = get_timezone(g.participation.user, g.contest)

    # some information about token configuration
    ret["tokens_contest"] = g.contest.token_mode

    t_tokens = set(t.token_mode for t in g.contest.tasks)
    if len(t_tokens) == 1:
        ret["tokens_tasks"] = next(iter(t_tokens))
    else:
        ret["tokens_tasks"] = TOKEN_MODE_MIXED

    return ret


def get_task(task_name):
    return g.session.query(Task) \
        .filter(Task.contest == g.contest) \
        .filter(Task.name == task_name) \
        .one_or_none()


def get_submission(task, submission_num):
    """Return the num-th contestant's submission on the given task.
    task (Task): a task for the contest that is being served.
    submission_num (str): a positive number, in decimal encoding.
    return (Submission|None): the submission_num-th submission, in
        chronological order, that was sent by the currently logged
        in contestant on the given task (None if not found).
    """
    return g.session.query(Submission) \
        .filter(Submission.participation == g.participation) \
        .filter(Submission.task == task) \
        .order_by(Submission.timestamp) \
        .offset(int(submission_num) - 1) \
        .first()


def get_user_test(task, user_test_num):
    """Return the num-th contestant's test on the given task.
    task (Task): a task for the contest that is being served.
    user_test_num (str): a positive number, in decimal encoding.
    return (UserTest|None): the user_test_num-th user test, in
        chronological order, that was sent by the currently logged
        in contestant on the given task (None if not found).
    """
    return g.session.query(UserTest) \
        .filter(UserTest.participation == g.participation) \
        .filter(UserTest.task == task) \
        .order_by(UserTest.timestamp) \
        .offset(int(user_test_num) - 1) \
        .first()

# TODO use flask machinery for these
def add_notification(subject, text, level):
    current_app.service.add_notification(
        g.participation.user.username, g.timestamp,
        g._(subject), g._(text), level)


def notify_success(subject, text):
    add_notification(subject, text, NOTIFICATION_SUCCESS)


def notify_warning(subject, text):
    add_notification(subject, text, NOTIFICATION_WARNING)


def notify_error(subject, text):
    add_notification(subject, text, NOTIFICATION_ERROR)
