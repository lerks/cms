#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2018 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import json
import logging
import unittest
from mock import patch
from future.backports.urllib.parse import urljoin
from xml.etree import ElementTree

from werkzeug.test import Client
from werkzeug.urls import Href
from werkzeug.wrappers import Response

# Needs to be first to allow for monkey patching the DB connection string.
from cmstestsuite.unit_tests.testdbgenerator import TestCaseWithDatabase

from cms.db import SubmissionFormatElement
from cms.server.contest import ContestWebServer
from cmscommon.crypto import build_password
from cmstestsuite.unit_tests.testidgenerator import unique_unicode_id


logger = logging.getLogger(__name__)


def add_line_numbers(text):
    res = list()
    for i, l in enumerate(text.splitlines(), start=1):
        res.append("%3d: %s" % (i, l))
    return "\n".join(res)


class TestCaseForCWS(TestCaseWithDatabase):

    MULTI_CONTEST = False

    @classmethod
    def setUpClass(cls):
        super(TestCaseForCWS, cls).setUpClass()

        cls.rpc_patcher = patch("cms.io.service.Service.connect_to")
        cls.MockClass = cls.rpc_patcher.start()

        # Hackish...
        cls.server = ContestWebServer(0, None if cls.MULTI_CONTEST else -1)

    @classmethod
    def tearDownClass(cls):
        cls.rpc_patcher.stop()
        super(TestCaseForCWS, cls).tearDownClass()

    def setUp(self):
        super(TestCaseForCWS, self).setUp()

        self.contest = self.add_contest()
        self.user = self.add_user(password=build_password(""))
        self.participation = self.add_participation(contest=self.contest,
                                                    user=self.user)
        self.task = self.add_task(contest=self.contest, submission_format=[SubmissionFormatElement("foo.%l")])
        self.dataset = self.add_dataset(
            task=self.task, task_type="Batch",
            task_type_parameters=["alone", ["", ""], "diff"], score_type="Sum", score_type_parameters=1
        )
        self.task.active_dataset = self.dataset
        self.submission = self.add_submission(participation=self.participation, task=self.task)
        self.user_test = self.add_user_test(participation=self.participation, task=self.task)
        self.session.commit()

        if not self.MULTI_CONTEST:
            self.server.contest_id = self.contest.id

        self.client = Client(
            self.server, response_wrapper=Response, use_cookies=True)

        self.href = Href("/")
        if self.MULTI_CONTEST:
            self.href = getattr(self.href, self.contest.name)

    def login(self):
        _, tree = self.get_as_html()
        # TODO print source if this fails?
        xsfr_cookie = tree.find(".//input[@name='_xsrf']").attrib["value"]
        response = self.client.post(self.href("login"), data={"username": self.user.username, "password": "", "_xsrf": xsfr_cookie})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urljoin(self.href("login"), response.location), self.href())

    def parse_html(self, response):
        self.assertEqual(response.mimetype, "text/html")
        try:
            tree = ElementTree.fromstring(response.data)
        except:
            logger.info(
                "Failed to parse the following response as HTML:\n%s",
                add_line_numbers(response.data.decode("utf-8",
                                                      errors="replace")))
            raise
        return response, tree

    def parse_json(self, response):
        self.assertEqual(response.mimetype, "application/json")
        try:
            data = json.loads(response.data)
        except ValueError:
            logger.info(
                "Failed to parse the following response as JSON:\n%s",
                add_line_numbers(response.data.decode("utf-8",
                                                      errors="replace")))
            raise
        return response, data

    def get(self, *args, **kwargs):
        url = self.href(*args, **kwargs)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response

    def get_as_html(self, *args, **kwargs):
        return self.parse_html(self.get(*args, **kwargs))

    def get_as_html_or_empty(self, *args, **kwargs):
        response = self.get(*args, **kwargs)
        if len(response.data.strip()) == 0:
            return response, None
        return self.parse_html(response)

    def get_as_json(self, *args, **kwargs):
        return self.parse_json(self.get(*args, **kwargs))

    def test_overview(self):
        self.login()
        self.get_as_html()

    def test_communication(self):
        self.login()
        self.get_as_html("communication")

    def test_task_description(self):
        self.login()
        self.get_as_html("tasks", self.task.name, "description")

    def test_task_submissions(self):
        self.login()
        self.get_as_html("tasks", self.task.name, "submissions")

    def test_test_interface(self):
        self.login()
        self.get_as_html("testing")

    def test_printing(self):
        self.login()
        self.get_as_html("printing")

        # TODO also submit to this

    def test_documentation(self):
        self.login()
        self.get_as_html("documentation")

    def test_submission_status(self):
        self.login()
        self.get_as_json("tasks", self.task.name, "submissions", 1)

    def test_submission_details(self):
        self.login()
        self.get_as_html_or_empty("tasks", self.task.name, "submissions", 1, "details")

    def test_user_test_status(self):
        self.login()
        self.get_as_json("tasks", self.task.name, "tests", 1)

    def test_user_test_details(self):
        self.login()
        self.get_as_html_or_empty("tasks", self.task.name, "tests", 1, "details")


    def submit_form(self, url, data, before=None, after=None):
        url = self.href(*url)
        if before is not None:
            _, tree = self.get_as_html(*before)
            # TODO print source if this fails?
            # TODO What if more than one?
            data["_xsrf"] = tree.find(".//input[@name='_xsrf']").attrib["value"]
        response = self.client.post(url, data=data)
        self.assertEqual(response.status_code, 302)
        if after is not None or before is not None:
            check_url = after or before
            self.assertEqual(urljoin(url, response.location),
                             self.href(*check_url))
        return response

    def test_ask_question(self):
        self.login()
        subject = unique_unicode_id()
        text = unique_unicode_id()
        self.submit_form(
            ["question"],
            {"question_subject": subject, "question_text": text},
            before=["communication"])

# (r"/tasks/(.*)/statements/(.*)", TaskStatementViewHandler),
# (r"/tasks/(.*)/attachments/(.*)", TaskAttachmentViewHandler),
# (r"/tasks/(.*)/submissions/([1-9][0-9]*)/files/(.*)", SubmissionFileHandler),
# (r"/tasks/(.*)/tests/([1-9][0-9]*)/(input|output)", UserTestIOHandler),
# (r"/tasks/(.*)/tests/([1-9][0-9]*)/files/(.*)", UserTestFileHandler),


# (r"/login", LoginHandler),
# (r"/logout", LogoutHandler),
# (r"/start", StartHandler),
# (r"/notifications", NotificationsHandler),
# (r"/tasks/(.*)/submit", SubmitHandler),
# (r"/tasks/(.*)/submissions/([1-9][0-9]*)/token", UseTokenHandler),
# (r"/tasks/(.*)/test", UserTestHandler),
# (r"/question", QuestionHandler),


class TestCaseForMultiContestCWS(TestCaseForCWS):

    MULTI_CONTEST = True

    def test_contest_list(self):
        pass


if __name__ == "__main__":
    unittest.main()

