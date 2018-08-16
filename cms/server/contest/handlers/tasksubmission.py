#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2018 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2016 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

"""Submission-related handlers for CWS for a specific task.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import logging
import re

import tornado.web

from sqlalchemy.orm import joinedload

from cms import config, FEEDBACK_LEVEL_FULL
from cms.db import Submission, SubmissionResult
from cms import config
from cms.db import File, Submission, SubmissionResult, Task, Token, \
    ScopedSession
from cms.grading.languagemanager import get_language
from cms.server import multi_contest
from cms.server.contest.submission import get_submission_count, \
    UnacceptableSubmission, accept_submission
from cms.server.contest.tokening import \
    UnacceptableToken, TokenAlreadyPlayed, accept_token, tokens_available
from cms.grading.scoretypes import get_score_type
from cms.grading.tasktypes import get_task_type
from cms.server import actual_phase_required, multi_contest
from cms.server.contest.handlers import contest_bp
from cms.server.contest.handlers.base import authentication_required, templated
from cmscommon.archive import Archive
from cmscommon.crypto import encrypt_number
from cmscommon.mimetypes import get_type_for_file_name

from ..phase_management import actual_phase_required

from .contest import ContestHandler, FileHandler


logger = logging.getLogger(__name__)


# Dummy function to mark translatable strings.
def N_(msgid):
    return msgid


@contest_bp.route("/tasks/<task_name>/submit", methods=["POST"])
@authentication_required()
@actual_phase_required(0, 3)
def submit_handler(task_name):
        """Handles the received submissions.

        """
        task = self.get_task(task_name)
        if task is None:
            raise tornado.web.HTTPError(404)

        # Only set the official bit when the user can compete and we are not in
        # analysis mode.
        official = self.r_params["actual_phase"] == 0

        query_args = dict()

        try:
            submission = accept_submission(
                self.sql_session, self.service.file_cacher, self.current_user,
                task, self.timestamp, self.request.files,
                self.get_argument("language", None), official)
            self.sql_session.commit()
        except UnacceptableSubmission as e:
            logger.info("Sent error: `%s' - `%s'", e.subject, e.text)
            self.notify_error(e.subject, e.text)
        else:
            self.service.evaluation_service.new_submission(
                submission_id=submission.id)
            self.notify_success(N_("Submission received"),
                                N_("Your submission has been received "
                                   "and is currently being evaluated."))
            # The argument (encrypted submission id) is not used by CWS
            # (nor it discloses information to the user), but it is
            # useful for automatic testing to obtain the submission id).
            query_args["submission_id"] = \
                encrypt_number(submission.id, config.secret_key)

        self.redirect(self.contest_url("tasks", task.name, "submissions",
                                       **query_args))


@contest_bp.route("/tasks/<task_name>/submissions", methods=["GET"])
@authentication_required()
@actual_phase_required(0, 3)
@templated("task_submissions.html")
def task_submissions_handler(task_name):
        """Shows the data of a task in the contest.

        """
        participation = g.participation

        task = self.get_task(task_name)
        if task is None:
            raise tornado.web.HTTPError(404)

        submissions = ScopedSession().query(Submission)\
            .filter(Submission.participation == participation)\
            .filter(Submission.task == task)\
            .options(joinedload(Submission.token))\
            .options(joinedload(Submission.results))\
            .all()

        submissions_left_contest = None
        if self.contest.max_submission_number is not None:
            submissions_c = \
                get_submission_count(self.sql_session, participation,
                                     contest=self.contest)
            submissions_left_contest = \
                g.contest.max_submission_number - submissions_c

        submissions_left_task = None
        if task.max_submission_number is not None:
            submissions_left_task = \
                task.max_submission_number - len(submissions)

        submissions_left = submissions_left_contest
        if submissions_left_task is not None and \
            (submissions_left_contest is None or
             submissions_left_contest > submissions_left_task):
            submissions_left = submissions_left_task

        # Make sure we do not show negative value if admins changed
        # the maximum
        if submissions_left is not None:
            submissions_left = max(0, submissions_left)

        tokens_info = tokens_available(participation, task, self.timestamp)

        download_allowed = self.contest.submissions_download_allowed
        self.render("task_submissions.html",
                    task=task, submissions=submissions,
                    tokens_info=tokens_info,
                    submissions_left=submissions_left,
                    submissions_download_allowed=download_allowed,
                    **self.r_params)


@contest_bp.route("/tasks/<task_name>/submissions/<int:submission_num>", methods=["POST"])
@authentication_required(refresh_cookie=False)
@actual_phase_required(0, 3)
def submission_status_handler(task_name, submission_num):
        task = self.get_task(task_name)
        if task is None:
            raise tornado.web.HTTPError(404)

        submission = self.get_submission(task, submission_num)
        if submission is None:
            raise tornado.web.HTTPError(404)

        sr = submission.get_result(task.active_dataset)
        data = dict()

        if sr is None:
            # implicit compiling state while result is not created
            data["status"] = SubmissionResult.COMPILING
        else:
            data["status"] = sr.get_status()

        if data["status"] == SubmissionResult.COMPILING:
            data["status_text"] = self._("Compiling...")
        elif data["status"] == SubmissionResult.COMPILATION_FAILED:
            data["status_text"] = "%s <a class=\"details\">%s</a>" % (
                self._("Compilation failed"), self._("details"))
        elif data["status"] == SubmissionResult.EVALUATING:
            data["status_text"] = self._("Evaluating...")
        elif data["status"] == SubmissionResult.SCORING:
            data["status_text"] = self._("Scoring...")
        elif data["status"] == SubmissionResult.SCORED:
            data["status_text"] = "%s <a class=\"details\">%s</a>" % (
                self._("Evaluated"), self._("details"))

            score_type = task.active_dataset.score_type_object
            if score_type.max_public_score > 0:
                data["max_public_score"] = \
                    round(score_type.max_public_score, task.score_precision)
                data["public_score"] = \
                    round(sr.public_score, task.score_precision)
                data["public_score_message"] = score_type.format_score(
                    sr.public_score, score_type.max_public_score,
                    sr.public_score_details, task.score_precision,
                    translation=self.translation)
            if submission.token is not None:
                data["max_score"] = \
                    round(score_type.max_score, task.score_precision)
                data["score"] = \
                    round(sr.score, task.score_precision)
                data["score_message"] = score_type.format_score(
                    sr.score, score_type.max_score,
                    sr.score_details, task.score_precision,
                    translation=self.translation)

        self.write(data)


@contest_bp.route("/tasks/<task_name>/submissions/<int:submission_num>/details", methods=["GET"])
@authentication_required(refresh_cookie=False)
@actual_phase_required(0, 3)
@templated("submission_details.html")
def submission_details_handler(task_name, submission_num):
        task = self.get_task(task_name)
        if task is None:
            raise tornado.web.HTTPError(404)

        submission = self.get_submission(task, submission_num)
        if submission is None:
            raise tornado.web.HTTPError(404)

        sr = submission.get_result(task.active_dataset)
        score_type = task.active_dataset.score_type_object

        details = None
        if sr is not None:
            if submission.tokened():
                details = sr.score_details
            else:
                details = sr.public_score_details

            if sr.scored():
                feedback_level = task.feedback_level
                # During analysis mode we show the full feedback regardless of
                # what the task says.
                if self.r_params["actual_phase"] == 3:
                    feedback_level = FEEDBACK_LEVEL_FULL
                details = score_type.get_html_details(
                    details, feedback_level, translation=self.translation)
            else:
                details = None

        return {"sr": sr, "details": details}


@contest_bp.route("/tasks/<task_name>/submissions/<int:submission_num>/files/<filename>", methods=["GET"])
@authentication_required()
@actual_phase_required(0, 3)
def submission_file_handler(task_name, submission_num, filename):
        """Send back a submission file.

        """
        if not self.contest.submissions_download_allowed:
            raise tornado.web.HTTPError(404)

        task = self.get_task(task_name)
        if task is None:
            raise tornado.web.HTTPError(404)

        submission = self.get_submission(task, submission_num)
        if submission is None:
            raise tornado.web.HTTPError(404)

        # The following code assumes that submission.files is a subset
        # of task.submission_format. CWS will always ensure that for new
        # submissions, yet, if the submission_format changes during the
        # competition, this may not hold anymore for old submissions.

        # filename is the name used by the browser, hence is something
        # like 'foo.c' (and the extension is CMS's preferred extension
        # for the language). To retrieve the right file, we need to
        # decode it to 'foo.%l'.
        stored_filename = filename
        if submission.language is not None:
            extension = get_language(submission.language).source_extension
            stored_filename = re.sub(r'%s$' % extension, '.%l', filename)

        if stored_filename not in submission.files:
            raise tornado.web.HTTPError(404)

        digest = submission.files[stored_filename].digest
        self.sql_session.close()

        mimetype = get_type_for_file_name(filename)
        if mimetype is None:
            mimetype = 'application/octet-stream'

        self.fetch(digest, mimetype, filename)


@contest_bp.route("/tasks/<task_name>/submissions/<int:submission_num>/token", methods=["POST"])
@authentication_required()
@actual_phase_required(0)
def use_token_handler(task_name, submission_num):
        """Called when the user try to use a token on a submission.

        """
        task = self.get_task(task_name)
        if task is None:
            raise tornado.web.HTTPError(404)

        submission = self.get_submission(task, submission_num)
        if submission is None:
            raise tornado.web.HTTPError(404)

        try:
            accept_token(self.sql_session, submission, self.timestamp)
            self.sql_session.commit()
        except UnacceptableToken as e:
            self.notify_error(e.subject, e.text)
        except TokenAlreadyPlayed as e:
            self.notify_warning(e.subject, e.text)
        else:
            # Inform ProxyService and eventually the ranking that the
            # token has been played.
            self.service.proxy_service.submission_tokened(
                submission_id=submission.id)

            logger.info("Token played by user %s on task %s.",
                        self.current_user.user.username, task.name)

            # Add "All ok" notification.
            self.notify_success(N_("Token request received"),
                                N_("Your request has been received "
                                   "and applied to the submission."))

        self.redirect(self.contest_url("tasks", task.name, "submissions"))
