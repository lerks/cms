#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

import unittest
from collections import namedtuple

from mock import Mock, MagicMock, PropertyMock, patch

import cms.grading.files
import cms.grading.tasktypes


FileSchema = namedtuple("FileSchema",
                        "language codename filename max_size optional")
UserFile = namedtuple("File",
                      "filename digest")
OtherFile = namedtuple("File",
                       "language codename digest")


class TestCmsGradingFiles(unittest.TestCase):
    def setUp(self):
        self.task_type = Mock()
        self.submission = Mock()
        self.dataset = Mock()
        self.submission_result = Mock()
        self.testcase = Mock()
        self.execution = Mock()

        for scope in ["task_type", "dataset"]:
            mock = getattr(self, scope)
            for type_ in ["user", "dataset", "compilation",
                          "testcase", "execution"]:
                file_schemas = []
                setattr(mock, "%s_file_schemas" % type_, file_schemas)

        for scope, type_ in [
                ("submission", "user"), ("dataset", "dataset"),
                ("submission_result", "compilation"),
                ("testcase", "testcase"), ("execution", "execution")]:
            mock = getattr(self, scope)
            prop = PropertyMock()
            prop.__get__ = lambda s: getattr(self, "%s_files" % type_)
            prop.__set__ = lambda s, v: setattr(self, "%s_files" % type_, v)
            setattr(mock, "%s_files" % type_, prop)
            setattr(self, "%s_files" % type_, [])

        patcher1 = patch("cms.grading.tasktypes.get_task_type")
        mock1 = patcher1.start()
        mock1.return_value = self.task_type
        self.addCleanup(patcher1.stop)

        patcher2 = patch("cms.grading.files.get_task_type")
        mock2 = patcher2.start()
        mock2.return_value = self.task_type
        self.addCleanup(patcher2.stop)

        logger = cms.grading.files.logger
        # Add wraps=logger to print logging output.
        patcher3 = patch("cms.grading.files.logger")
        self.logger = patcher3.start()
        self.addCleanup(patcher3.stop)


class SingleSchemaSet(TestCmsGradingFiles):
    VALUES_1 = [("c", "foo", "foo.c", 42, False)]
    EXPECT_1 = {"foo": ("foo.c", 42, False)}

    VALUES_2 = [("c", "foo", "foo.c", 42, False),
                ("cpp", "foo", "foo.cpp", 43, True)]
    EXPECT_2 = {"foo": ("foo.c", 42, False)}

    VALUES_3 = [("c", "foo", "foo.c", 42, False),
                (None, "foo", "foo.txt", 42, False)]

    VALUES_4 = [("c", "foo", "foo.c", 42, False)]
    EXPECT_4 = {}

    VALUES_5T = [("c", "foo1", "foo1.c", 42, False),
                 ("c", "foo2", "foo2.c", 42, False),
                 (None, "foo3", "foo3.c", None, True),
                 (None, "foo4", "foo4.c", None, True)]
    VALUES_5D = [("c", "foo1", "bar1.c", 43, False),
                 (None, "foo2", "bar2.c", None, True),
                 ("c", "foo3", "bar3.c", 42, False),
                 (None, "foo4", "bar4.c", None, True)]
    EXPECT_5 = {"foo1": ("bar1.c", 43, False),
                "foo2": ("bar2.c", None, False),
                "foo3": ("bar3.c", 42, False),
                "foo4": ("bar4.c", None, True)}

    def helper(self, method, type_, task_type, dataset, result_p, result_e,
               success=True, warning=False):
        getattr(self.task_type, "%s_file_schemas" % type_).extend(
            FileSchema(*v) for v in task_type)
        getattr(self.dataset, "%s_file_schemas" % type_).extend(
            FileSchema(*v) for v in dataset)

        method = getattr(cms.grading.files, "get_format_for_%s" % method)

        if success:
            actual_p, actual_e = method(self.dataset, "c", "operation")
            self.assertDictEqual(actual_p, result_p)
            self.assertDictEqual(actual_e, result_e)
            self.assertFalse(self.logger.error.called)
        else:
            with self.assertRaises(ValueError):
                method(self.dataset, "c", "operation")
            self.assertTrue(self.logger.error.called)

        if warning:
            self.assertTrue(self.logger.warning.called)
        else:
            self.assertFalse(self.logger.warning.called)

    ### User File Schemas

    ## Compilation

    def test_compilation_on_user_file_schemas_1t(self):
        self.helper("compilation", "user", self.VALUES_1, [], self.EXPECT_1, {})

    def test_compilation_on_user_file_schemas_2t(self):
        self.helper("compilation", "user", self.VALUES_2, [], self.EXPECT_2, {})

    def test_compilation_on_user_file_schemas_3t(self):
        self.helper("compilation", "user", self.VALUES_3, [], {}, {}, success=False)

    def test_compilation_on_user_file_schemas_1d(self):
        self.helper("compilation", "user", [], self.VALUES_1, {}, {}, warning=True)

    def test_compilation_on_user_file_schemas_2d(self):
        self.helper("compilation", "user", [], self.VALUES_2, {}, {}, warning=True)

    def test_compilation_on_user_file_schemas_3d(self):
        self.helper("compilation", "user", [], self.VALUES_3, {}, {}, success=False)

    def test_compilation_on_user_file_schemas_4(self):
        self.helper("compilation", "user", [], self.VALUES_4, self.EXPECT_4, {}, warning=True)

    def test_compilation_on_user_file_schemas_5(self):
        self.helper("compilation", "user", self.VALUES_5T, self.VALUES_5D, self.EXPECT_5, {})

    ## Evaluation

    def test_evaluation_on_user_file_schemas_1t(self):
        self.helper("evaluation", "user", self.VALUES_1, [], self.EXPECT_1, {})

    def test_evaluation_on_user_file_schemas_2t(self):
        self.helper("evaluation", "user", self.VALUES_2, [], self.EXPECT_2, {})

    def test_evaluation_on_user_file_schemas_3t(self):
        self.helper("evaluation", "user", self.VALUES_3, [], {}, {}, success=False)

    def test_evaluation_on_user_file_schemas_1d(self):
        self.helper("evaluation", "user", [], self.VALUES_1, {}, {}, warning=True)

    def test_evaluation_on_user_file_schemas_2d(self):
        self.helper("evaluation", "user", [], self.VALUES_2, {}, {}, warning=True)

    def test_evaluation_on_user_file_schemas_3d(self):
        self.helper("evaluation", "user", [], self.VALUES_3, {}, {}, success=False)

    def test_evaluation_on_user_file_schemas_4(self):
        self.helper("evaluation", "user", [], self.VALUES_4, self.EXPECT_4, {}, warning=True)

    def test_evaluation_on_user_file_schemas_5(self):
        self.helper("evaluation", "user", self.VALUES_5T, self.VALUES_5D, self.EXPECT_5, {})

    ### Dataset File Schemas

    ## Compilation

    def test_compilation_on_dataset_file_schemas_1t(self):
        self.helper("compilation", "dataset", self.VALUES_1, [], self.EXPECT_1, {})

    def test_compilation_on_dataset_file_schemas_2t(self):
        self.helper("compilation", "dataset", self.VALUES_2, [], self.EXPECT_2, {})

    def test_compilation_on_dataset_file_schemas_3t(self):
        self.helper("compilation", "dataset", self.VALUES_3, [], {}, {}, success=False)

    def test_compilation_on_dataset_file_schemas_1d(self):
        self.helper("compilation", "dataset", [], self.VALUES_1, {}, {}, warning=True)

    def test_compilation_on_dataset_file_schemas_2d(self):
        self.helper("compilation", "dataset", [], self.VALUES_2, {}, {}, warning=True)

    def test_compilation_on_dataset_file_schemas_3d(self):
        self.helper("compilation", "dataset", [], self.VALUES_3, {}, {}, success=False)

    def test_compilation_on_dataset_file_schemas_4(self):
        self.helper("compilation", "dataset", [], self.VALUES_4, self.EXPECT_4, {}, warning=True)

    def test_compilation_on_dataset_file_schemas_5(self):
        self.helper("compilation", "dataset", self.VALUES_5T, self.VALUES_5D, self.EXPECT_5, {})

    # Evaluation

    def test_evaluation_on_dataset_file_schemas_1t(self):
        self.helper("evaluation", "dataset", self.VALUES_1, [], self.EXPECT_1, {})

    def test_evaluation_on_dataset_file_schemas_2t(self):
        self.helper("evaluation", "dataset", self.VALUES_2, [], self.EXPECT_2, {})

    def test_evaluation_on_dataset_file_schemas_3t(self):
        self.helper("evaluation", "dataset", self.VALUES_3, [], {}, {}, success=False)

    def test_evaluation_on_dataset_file_schemas_1d(self):
        self.helper("evaluation", "dataset", [], self.VALUES_1, {}, {}, warning=True)

    def test_evaluation_on_dataset_file_schemas_2d(self):
        self.helper("evaluation", "dataset", [], self.VALUES_2, {}, {}, warning=True)

    def test_evaluation_on_dataset_file_schemas_3d(self):
        self.helper("evaluation", "dataset", [], self.VALUES_3, {}, {}, success=False)

    def test_evaluation_on_dataset_file_schemas_4(self):
        self.helper("evaluation", "dataset", [], self.VALUES_4, self.EXPECT_4, {}, warning=True)

    def test_evaluation_on_dataset_file_schemas_5(self):
        self.helper("evaluation", "dataset", self.VALUES_5T, self.VALUES_5D, self.EXPECT_5, {})

    ### Compilation File Schemas

    ## Compilation

    def test_compilation_on_compilation_file_schemas_1t(self):
        self.helper("compilation", "compilation", self.VALUES_1, [], {}, self.EXPECT_1)

    def test_compilation_on_compilation_file_schemas_2t(self):
        self.helper("compilation", "compilation", self.VALUES_2, [], {}, self.EXPECT_2)

    def test_compilation_on_compilation_file_schemas_3t(self):
        self.helper("compilation", "compilation", self.VALUES_3, [], {}, {}, success=False)

    def test_compilation_on_compilation_file_schemas_1d(self):
        self.helper("compilation", "compilation", [], self.VALUES_1, {}, {}, warning=True)

    def test_compilation_on_compilation_file_schemas_2d(self):
        self.helper("compilation", "compilation", [], self.VALUES_2, {}, {}, warning=True)

    def test_compilation_on_compilation_file_schemas_3d(self):
        self.helper("compilation", "compilation", [], self.VALUES_3, {}, {}, success=False)

    def test_compilation_on_compilation_file_schemas_4(self):
        self.helper("compilation", "compilation", [], self.VALUES_4, {}, self.EXPECT_4, warning=True)

    def test_compilation_on_compilation_file_schemas_5(self):
        self.helper("compilation", "compilation", self.VALUES_5T, self.VALUES_5D, {}, self.EXPECT_5)

    ## Evaluation

    def test_evaluation_on_compilation_file_schemas_1t(self):
        self.helper("evaluation", "compilation", self.VALUES_1, [], self.EXPECT_1, {})

    def test_evaluation_on_compilation_file_schemas_2t(self):
        self.helper("evaluation", "compilation", self.VALUES_2, [], self.EXPECT_2, {})

    def test_evaluation_on_compilation_file_schemas_3t(self):
        self.helper("evaluation", "compilation", self.VALUES_3, [], {}, {}, success=False)

    def test_evaluation_on_compilation_file_schemas_1d(self):
        self.helper("evaluation", "compilation", [], self.VALUES_1, {}, {}, warning=True)

    def test_evaluation_on_compilation_file_schemas_2d(self):
        self.helper("evaluation", "compilation", [], self.VALUES_2, {}, {}, warning=True)

    def test_evaluation_on_compilation_file_schemas_3d(self):
        self.helper("evaluation", "compilation", [], self.VALUES_3, {}, {}, success=False)

    def test_evaluation_on_compilation_file_schemas_4(self):
        self.helper("evaluation", "compilation", [], self.VALUES_4, self.EXPECT_4, {}, warning=True)

    def test_evaluation_on_compilation_file_schemas_5(self):
        self.helper("evaluation", "compilation", self.VALUES_5T, self.VALUES_5D, self.EXPECT_5, {})

    ### Testcase File Schemas

    ## Compilation

    def test_compilation_on_testcase_file_schemas_1t(self):
        self.helper("compilation", "testcase", self.VALUES_1, [], {}, {})

    def test_compilation_on_testcase_file_schemas_2t(self):
        self.helper("compilation", "testcase", self.VALUES_2, [], {}, {})

    def test_compilation_on_testcase_file_schemas_3t(self):
        self.helper("compilation", "testcase", self.VALUES_3, [], {}, {})

    def test_compilation_on_testcase_file_schemas_1d(self):
        self.helper("compilation", "testcase", [], self.VALUES_1, {}, {})

    def test_compilation_on_testcase_file_schemas_2d(self):
        self.helper("compilation", "testcase", [], self.VALUES_2, {}, {})

    def test_compilation_on_testcase_file_schemas_3d(self):
        self.helper("compilation", "testcase", [], self.VALUES_3, {}, {})

    def test_compilation_on_testcase_file_schemas_4(self):
        self.helper("compilation", "testcase", [], self.VALUES_4, {}, {})

    def test_compilation_on_testcase_file_schemas_5(self):
        self.helper("compilation", "testcase", self.VALUES_5T, self.VALUES_5D, {}, {})

    ## Evaluation

    def test_evaluation_on_testcase_file_schemas_1t(self):
        self.helper("evaluation", "testcase", self.VALUES_1, [], self.EXPECT_1, {})

    def test_evaluation_on_testcase_file_schemas_2t(self):
        self.helper("evaluation", "testcase", self.VALUES_2, [], self.EXPECT_2, {})

    def test_evaluation_on_testcase_file_schemas_3t(self):
        self.helper("evaluation", "testcase", self.VALUES_3, [], {}, {}, success=False)

    def test_evaluation_on_testcase_file_schemas_1d(self):
        self.helper("evaluation", "testcase", [], self.VALUES_1, {}, {}, warning=True)

    def test_evaluation_on_testcase_file_schemas_2d(self):
        self.helper("evaluation", "testcase", [], self.VALUES_2, {}, {}, warning=True)

    def test_evaluation_on_testcase_file_schemas_3d(self):
        self.helper("evaluation", "testcase", [], self.VALUES_3, {}, {}, success=False)

    def test_evaluation_on_testcase_file_schemas_4(self):
        self.helper("evaluation", "testcase", [], self.VALUES_4, self.EXPECT_4, {}, warning=True)

    def test_evaluation_on_testcase_file_schemas_5(self):
        self.helper("evaluation", "testcase", self.VALUES_5T, self.VALUES_5D, self.EXPECT_5, {})

    ### Execution File Schemas

    ## Compilation

    def test_compilation_on_execution_file_schemas_1t(self):
        self.helper("compilation", "execution", self.VALUES_1, [], {}, {})

    def test_compilation_on_execution_file_schemas_2t(self):
        self.helper("compilation", "execution", self.VALUES_2, [], {}, {})

    def test_compilation_on_execution_file_schemas_3t(self):
        self.helper("compilation", "execution", self.VALUES_3, [], {}, {})

    def test_compilation_on_execution_file_schemas_1d(self):
        self.helper("compilation", "execution", [], self.VALUES_1, {}, {})

    def test_compilation_on_execution_file_schemas_2d(self):
        self.helper("compilation", "execution", [], self.VALUES_2, {}, {})

    def test_compilation_on_execution_file_schemas_3d(self):
        self.helper("compilation", "execution", [], self.VALUES_3, {}, {})

    def test_compilation_on_execution_file_schemas_4(self):
        self.helper("compilation", "execution", [], self.VALUES_4, {}, {})

    def test_compilation_on_execution_file_schemas_5(self):
        self.helper("compilation", "execution", self.VALUES_5T, self.VALUES_5D, {}, {})

    ## Evaluation

    def test_evaluation_on_execution_file_schemas_1t(self):
        self.helper("evaluation", "execution", self.VALUES_1, [], {}, self.EXPECT_1)

    def test_evaluation_on_execution_file_schemas_2t(self):
        self.helper("evaluation", "execution", self.VALUES_2, [], {}, self.EXPECT_2)

    def test_evaluation_on_execution_file_schemas_3t(self):
        self.helper("evaluation", "execution", self.VALUES_3, [], {}, {}, success=False)

    def test_evaluation_on_execution_file_schemas_1d(self):
        self.helper("evaluation", "execution", [], self.VALUES_1, {}, {}, warning=True)

    def test_evaluation_on_execution_file_schemas_2d(self):
        self.helper("evaluation", "execution", [], self.VALUES_2, {}, {}, warning=True)

    def test_evaluation_on_execution_file_schemas_3d(self):
        self.helper("evaluation", "execution", [], self.VALUES_3, {}, {}, success=False)

    def test_evaluation_on_execution_file_schemas_4(self):
        self.helper("evaluation", "execution", [], self.VALUES_4, {}, self.EXPECT_4, warning=True)

    def test_evaluation_on_execution_file_schemas_5(self):
        self.helper("evaluation", "execution", self.VALUES_5T, self.VALUES_5D, {}, self.EXPECT_5)


class MultiSchemaSet(TestCmsGradingFiles):
    # We assume that if overrides work with single sets they also work
    # with multiple merged sets. We therefore just test merging of file
    # schemas defined at TaskType level.
    VALUES = [("c", "foo1", "foo1.c", 42, False),
              ("c", "foo2", "foo2.c", 42, False),
              ("c", "foo3", "foo3.c", 42, False),
              ("c", "foo4", "foo4.c", 42, False),
              ("c", "foo5", "foo5.c", 42, False)]

    def helper(self, method, user=[], dataset=[], compilation=[],
               testcase=[], execution=[], result_p=[], result_e=[],
               success=True, warning=False):
        self.task_type.user_file_schemas.extend(
            FileSchema(*v) for v in user)
        self.task_type.dataset_file_schemas.extend(
            FileSchema(*v) for v in dataset)
        self.task_type.compilation_file_schemas.extend(
            FileSchema(*v) for v in compilation)
        self.task_type.testcase_file_schemas.extend(
            FileSchema(*v) for v in testcase)
        self.task_type.execution_file_schemas.extend(
            FileSchema(*v) for v in execution)

        method = getattr(cms.grading.files, "get_format_for_%s" % method)
        result_p = {k: [v[2:] for v in self.VALUES if v[1] == k][0] for k in result_p}
        result_e = {k: [v[2:] for v in self.VALUES if v[1] == k][0] for k in result_e}

        if success:
            actual_p, actual_e = method(self.dataset, "c", "operation")
            self.assertDictEqual(actual_p, result_p)
            self.assertDictEqual(actual_e, result_e)
            self.assertFalse(self.logger.error.called)
        else:
            with self.assertRaises(ValueError):
                method(self.dataset, "c", "operation")
            self.assertTrue(self.logger.error.called)

        if warning:
            self.assertTrue(self.logger.warning.called)
        else:
            self.assertFalse(self.logger.warning.called)

    ## Compilation

    def test_compilation_on_user_dataset(self):
        self.helper("compilation", user=[self.VALUES[0]], dataset=[self.VALUES[1]], result_p=["foo1", "foo2"])

    def test_compilation_on_user_compilation(self):
        self.helper("compilation", user=[self.VALUES[0]], compilation=[self.VALUES[1]], result_p=["foo1"], result_e=["foo2"])

    def test_compilation_on_user_testcase(self):
        self.helper("compilation", user=[self.VALUES[0]], testcase=[self.VALUES[1]], result_p=["foo1"])

    def test_compilation_on_user_execution(self):
        self.helper("compilation", user=[self.VALUES[0]], execution=[self.VALUES[1]], result_p=["foo1"])

    def test_compilation_on_dataset_compilation(self):
        self.helper("compilation", dataset=[self.VALUES[0]], compilation=[self.VALUES[1]], result_p=["foo1"], result_e=["foo2"])

    def test_compilation_on_dataset_testcase(self):
        self.helper("compilation", dataset=[self.VALUES[0]], testcase=[self.VALUES[1]], result_p=["foo1"])

    def test_compilation_on_dataset_execution(self):
        self.helper("compilation", dataset=[self.VALUES[0]], execution=[self.VALUES[1]], result_p=["foo1"])

    def test_compilation_on_compilation_testcase(self):
        self.helper("compilation", compilation=[self.VALUES[0]], testcase=[self.VALUES[1]], result_e=["foo1"])

    def test_compilation_on_compilation_execution(self):
        self.helper("compilation", compilation=[self.VALUES[0]], execution=[self.VALUES[1]], result_e=["foo1"])

    def test_compilation_on_testcase_execution(self):
        self.helper("compilation", testcase=[self.VALUES[0]], execution=[self.VALUES[1]])

    def test_compilation_on_user_dataset_conflict(self):
        self.helper("compilation", user=[self.VALUES[0]], dataset=[self.VALUES[0]], success=False)

    def test_compilation_on_user_compilation_conflict(self):
        self.helper("compilation", user=[self.VALUES[0]], compilation=[self.VALUES[0]], success=False)

    def test_compilation_on_user_testcase_conflict(self):
        self.helper("compilation", user=[self.VALUES[0]], testcase=[self.VALUES[0]], result_p=["foo1"])

    def test_compilation_on_user_execution_conflict(self):
        self.helper("compilation", user=[self.VALUES[0]], execution=[self.VALUES[0]], result_p=["foo1"])

    def test_compilation_on_dataset_compilation_conflict(self):
        self.helper("compilation", dataset=[self.VALUES[0]], compilation=[self.VALUES[0]], success=False)

    def test_compilation_on_dataset_testcase_conflict(self):
        self.helper("compilation", dataset=[self.VALUES[0]], testcase=[self.VALUES[0]], result_p=["foo1"])

    def test_compilation_on_dataset_execution_conflict(self):
        self.helper("compilation", dataset=[self.VALUES[0]], execution=[self.VALUES[0]], result_p=["foo1"])

    def test_compilation_on_compilation_testcase_conflict(self):
        self.helper("compilation", compilation=[self.VALUES[0]], testcase=[self.VALUES[0]], result_e=["foo1"])

    def test_compilation_on_compilation_execution_conflict(self):
        self.helper("compilation", compilation=[self.VALUES[0]], execution=[self.VALUES[0]], result_e=["foo1"])

    def test_compilation_on_testcase_execution_conflict(self):
        self.helper("compilation", testcase=[self.VALUES[0]], execution=[self.VALUES[0]])

    def test_compilation_in_general(self):
        self.helper("compilation", user=[self.VALUES[0]], dataset=[self.VALUES[1]], compilation=[self.VALUES[2]], testcase=[self.VALUES[3]], execution=[self.VALUES[4]], result_p=["foo1", "foo2"], result_e=["foo3"])

    ## Evaluation

    def test_evaluation_on_user_dataset(self):
        self.helper("evaluation", user=[self.VALUES[0]], dataset=[self.VALUES[1]], result_p=["foo1", "foo2"])

    def test_evaluation_on_user_compilation(self):
        self.helper("evaluation", user=[self.VALUES[0]], compilation=[self.VALUES[1]], result_p=["foo1", "foo2"])

    def test_evaluation_on_user_testcase(self):
        self.helper("evaluation", user=[self.VALUES[0]], testcase=[self.VALUES[1]], result_p=["foo1", "foo2"])

    def test_evaluation_on_user_execution(self):
        self.helper("evaluation", user=[self.VALUES[0]], execution=[self.VALUES[1]], result_p=["foo1"], result_e=["foo2"])

    def test_evaluation_on_dataset_compilation(self):
        self.helper("evaluation", dataset=[self.VALUES[0]], compilation=[self.VALUES[1]], result_p=["foo1", "foo2"])

    def test_evaluation_on_dataset_testcase(self):
        self.helper("evaluation", dataset=[self.VALUES[0]], testcase=[self.VALUES[1]], result_p=["foo1", "foo2"])

    def test_evaluation_on_dataset_execution(self):
        self.helper("evaluation", dataset=[self.VALUES[0]], execution=[self.VALUES[1]], result_p=["foo1"], result_e=["foo2"])

    def test_evaluation_on_compilation_testcase(self):
        self.helper("evaluation", compilation=[self.VALUES[0]], testcase=[self.VALUES[1]], result_p=["foo1", "foo2"])

    def test_evaluation_on_compilation_execution(self):
        self.helper("evaluation", compilation=[self.VALUES[0]], execution=[self.VALUES[1]], result_p=["foo1"], result_e=["foo2"])

    def test_evaluation_on_testcase_execution(self):
        self.helper("evaluation", testcase=[self.VALUES[0]], execution=[self.VALUES[1]], result_p=["foo1"], result_e=["foo2"])

    def test_evaluation_on_user_dataset_conflict(self):
        self.helper("evaluation", user=[self.VALUES[0]], dataset=[self.VALUES[0]], success=False)

    def test_evaluation_on_user_compilation_conflict(self):
        self.helper("evaluation", user=[self.VALUES[0]], compilation=[self.VALUES[0]], success=False)

    def test_evaluation_on_user_testcase_conflict(self):
        self.helper("evaluation", user=[self.VALUES[0]], testcase=[self.VALUES[0]], success=False)

    def test_evaluation_on_user_execution_conflict(self):
        self.helper("evaluation", user=[self.VALUES[0]], execution=[self.VALUES[0]], success=False)

    def test_evaluation_on_dataset_compilation_conflict(self):
        self.helper("evaluation", dataset=[self.VALUES[0]], compilation=[self.VALUES[0]], success=False)

    def test_evaluation_on_dataset_testcase_conflict(self):
        self.helper("evaluation", dataset=[self.VALUES[0]], testcase=[self.VALUES[0]], success=False)

    def test_evaluation_on_dataset_execution_conflict(self):
        self.helper("evaluation", dataset=[self.VALUES[0]], execution=[self.VALUES[0]], success=False)

    def test_evaluation_on_compilation_testcase_conflict(self):
        self.helper("evaluation", compilation=[self.VALUES[0]], testcase=[self.VALUES[0]], success=False)

    def test_evaluation_on_compilation_execution_conflict(self):
        self.helper("evaluation", compilation=[self.VALUES[0]], execution=[self.VALUES[0]], success=False)

    def test_evaluation_on_testcase_execution_conflict(self):
        self.helper("evaluation", testcase=[self.VALUES[0]], execution=[self.VALUES[0]], success=False)

    def test_evaluation_in_general(self):
        self.helper("evaluation", user=[self.VALUES[0]], dataset=[self.VALUES[1]], compilation=[self.VALUES[2]], testcase=[self.VALUES[3]], execution=[self.VALUES[4]], result_p=["foo1", "foo2", "foo3", "foo4"], result_e=["foo5"])


if __name__ == "__main__":
    unittest.main()
