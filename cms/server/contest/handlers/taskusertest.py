#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2018 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
# Copyright © 2015-2016 William Di Luigi <williamdiluigi@gmail.com>
# Copyright © 2016 Myungwoo Chun <mc.tamaki@gmail.com>
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

"""Usertest-related handlers for CWS for a specific task.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import logging
import re

from flask import g, request, redirect, abort, url_for, current_app, jsonify

from cms import config
from cms.db import UserTest, UserTestResult
from cms.grading.languagemanager import get_language
from cms.server.contest.submission import get_submission_count, \
    TestingNotAllowed, UnacceptableUserTest, accept_user_test
from cmscommon.crypto import encrypt_number
from cmscommon.mimetypes import get_type_for_file_name

from . import contest_bp, authentication_required, actual_phase_required, \
    templated, get_task, get_user_test, fetch, notify_error, notify_success


logger = logging.getLogger(__name__)


# Dummy function to mark translatable strings.
def N_(msgid):
    return msgid


@contest_bp.route("/testing", methods=["GET"])
@authentication_required()
@actual_phase_required(0)
@templated("test_interface.html")
def user_test_interface_handler():
        """Serve the interface to test programs.

        """
        if not g.contest.allow_user_tests:
            raise HTTPException(404)

        user_tests = dict()
        user_tests_left = dict()
        default_task = None

        user_tests_left_contest = None
        if g.contest.max_user_test_number is not None:
            user_test_c = \
                get_submission_count(g.session, g.participation,
                                     contest=g.contest, cls=UserTest)
            user_tests_left_contest = \
                g.contest.max_user_test_number - user_test_c

        for task in g.contest.tasks:
            if request.args.get("task_name", None) == task.name:
                default_task = task
            user_tests[task.id] = g.session.query(UserTest)\
                .filter(UserTest.participation == g.participation)\
                .filter(UserTest.task == task)\
                .all()
            user_tests_left_task = None
            if task.max_user_test_number is not None:
                user_tests_left_task = \
                    task.max_user_test_number - len(user_tests[task.id])

            user_tests_left[task.id] = user_tests_left_contest
            if user_tests_left_task is not None and \
                (user_tests_left_contest is None or
                 user_tests_left_contest > user_tests_left_task):
                user_tests_left[task.id] = user_tests_left_task

            # Make sure we do not show negative value if admins changed
            # the maximum
            if user_tests_left[task.id] is not None:
                user_tests_left[task.id] = max(0, user_tests_left[task.id])

        if default_task is None and len(g.contest.tasks) > 0:
            default_task = g.contest.tasks[0]

        return {"default_task": default_task,
                "user_tests": user_tests,
                "user_tests_left": user_tests_left,
                "UserTestResult": UserTestResult}


@contest_bp.route("/tasks/<task_name>/test", methods=["POST"])
@authentication_required(refresh_cookie=False)
@actual_phase_required(0)
def user_test_handler(task_name):
        if not g.contest.allow_user_tests:
            raise HTTPException(404)

        task = get_task(task_name)
        if task is None:
            raise HTTPException(404)

        query_args = dict()

        try:
            user_test = accept_user_test(
                g.session, current_app.service.file_cacher, g.participation,
                task, g.timestamp, request.files.to_dict(flat=False),
                request.form.get("language", None))
            g.session.commit()
        except TestingNotAllowed:
            logger.warning("User %s tried to make test on task %s.",
                           g.participation.user.username, task_name)
            raise HTTPException(404)
        except UnacceptableUserTest as e:
            logger.info("Sent error: `%s' - `%s'", e.subject, e.text)
            notify_error(e.subject, e.text)
        else:
            current_app.service.evaluation_service.new_user_test(
                user_test_id=user_test.id)
            notify_success(N_("Test received"),
                           N_("Your test has been received "
                              "and is currently being executed."))
            # The argument (encrypted user test id) is not used by CWS
            # (nor it discloses information to the user), but it is
            # useful for automatic testing to obtain the user test id).
            query_args["user_test_id"] = \
                encrypt_number(user_test.id, config.secret_key)

        return redirect(url_for("contest.user_test_interface_handler",
                                task_name=task.name, **query_args))


@contest_bp.route("/tasks/<task_name>/tests/<int:user_test_num>", methods=["GET"])
@authentication_required(refresh_cookie=False)
@actual_phase_required(0)
def user_test_status_handler(task_name, user_test_num):
        if not g.contest.allow_user_tests:
            raise HTTPException(404)

        task = get_task(task_name)
        if task is None:
            raise HTTPException(404)

        user_test = get_user_test(task, user_test_num)
        if user_test is None:
            raise HTTPException(404)

        ur = user_test.get_result(task.active_dataset)
        data = dict()

        if ur is None:
            data["status"] = UserTestResult.COMPILING
        else:
            data["status"] = ur.get_status()

        if data["status"] == UserTestResult.COMPILING:
            data["status_text"] = g._("Compiling...")
        elif data["status"] == UserTestResult.COMPILATION_FAILED:
            data["status_text"] = "%s <a class=\"details\">%s</a>" % (
                g._("Compilation failed"), g._("details"))
        elif data["status"] == UserTestResult.EVALUATING:
            data["status_text"] = g._("Executing...")
        elif data["status"] == UserTestResult.EVALUATED:
            data["status_text"] = "%s <a class=\"details\">%s</a>" % (
                g._("Executed"), g._("details"))

            if ur.execution_time is not None:
                data["time"] = \
                    g.translation.format_duration(ur.execution_time)
            else:
                data["time"] = None

            if ur.execution_memory is not None:
                data["memory"] = \
                    g.translation.format_size(ur.execution_memory)
            else:
                data["memory"] = None

            data["output"] = ur.output is not None

        return jsonify(data)


@contest_bp.route("/tasks/<task_name>/tests/<int:user_test_num>/details", methods=["GET"])
@authentication_required(refresh_cookie=False)
@actual_phase_required(0)
@templated("user_test_details.html")
def user_test_details_handler(task_name, user_test_num):
        if not g.contest.allow_user_tests:
            raise HTTPException(404)

        task = get_task(task_name)
        if task is None:
            raise HTTPException(404)

        user_test = get_user_test(task, user_test_num)
        if user_test is None:
            raise HTTPException(404)

        tr = user_test.get_result(task.active_dataset)

        return {"task": task,
                "tr": tr}


@contest_bp.route("/tasks/<task_name>/tests/<int:user_test_num>/<any(input, output):io>", methods=["GET"])
@authentication_required()
@actual_phase_required(0)
def user_test_io_handler(task_name, user_test_num, io):
        """Send back a submission file.

        """
        if not g.contest.allow_user_tests:
            raise HTTPException(404)

        task = get_task(task_name)
        if task is None:
            raise HTTPException(404)

        user_test = get_user_test(task, user_test_num)
        if user_test is None:
            raise HTTPException(404)

        if io == "input":
            digest = user_test.input
        else:  # io == "output"
            tr = user_test.get_result(task.active_dataset)
            digest = tr.output if tr is not None else None
        g.session.close()

        if digest is None:
            raise HTTPException(404)

        mimetype = 'text/plain'

        fetch(digest, mimetype, io)


@contest_bp.route("/tasks/<task_name>/tests/<int:user_test_num>/files/<filename>", methods=["GET"])
@authentication_required()
@actual_phase_required(0)
def user_test_file_handler(task_name, user_test_num, filename):
        """Send back a submission file.

        """
        if not g.contest.allow_user_tests:
            raise HTTPException(404)

        task = get_task(task_name)
        if task is None:
            raise HTTPException(404)

        user_test = get_user_test(task, user_test_num)
        if user_test is None:
            raise HTTPException(404)

        # filename is the name used by the browser, hence is something
        # like 'foo.c' (and the extension is CMS's preferred extension
        # for the language). To retrieve the right file, we need to
        # decode it to 'foo.%l'.
        stored_filename = filename
        if user_test.language is not None:
            extension = get_language(user_test.language).source_extension
            stored_filename = re.sub(r'%s$' % extension, '.%l', filename)

        if stored_filename in user_test.files:
            digest = user_test.files[stored_filename].digest
        elif stored_filename in user_test.managers:
            digest = user_test.managers[stored_filename].digest
        else:
            raise HTTPException(404)
        g.session.close()

        mimetype = get_type_for_file_name(filename)
        if mimetype is None:
            mimetype = 'application/octet-stream'

        fetch(digest, mimetype, filename)
