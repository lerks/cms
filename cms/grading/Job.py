#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2013-2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2013 Stefano Maggiolo <s.maggiolo@gmail.com>
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

"""A JobGroup is an abstraction of an "atomic" action of a Worker.

Jobs play a major role in the interface with TaskTypes: they are a
data structure containing all information about what the TaskTypes
should do. They are mostly used in the communication between ES and
the Workers, hence they contain only serializable data (for example,
the name of the task type, not the task type object itself).

A JobGroup represents an indivisible action of a Worker, that is, a
compilation or an evaluation. It contains one or more Jobs, for
example "compile the submission" or "evaluate the submission on a
certain testcase".

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import json
from copy import deepcopy

from cms.db import CompilationFile, EvaluationFile
from cms.grading.files import File, FileSchema, \
    get_format_for_compilation, get_files_for_compilation, \
    get_format_for_evaluation, get_files_for_evaluation


class Job(object):
    """Base class for all jobs.

    Input data (usually filled by ES): task_type,
    task_type_parameters. Metadata: shard, sandboxes, info.

    """

    # TODO Move 'success' inside Job.

    def __init__(self, task_type=None, task_type_parameters=None,
                 shard=None, sandboxes=None, info=None):
        """Initialization.

        task_type (string|None): the name of the task type.
        task_type_parameters (string|None): the parameters for the
            creation of the correct task type.
        shard (int|None): the shard of the Worker completing this job.
        sandboxes ([string]|None): the paths of the sandboxes used in
            the Worker during the execution of the job.
        info (string|None): a human readable description of the job.

        """
        if task_type is None:
            task_type = ""
        if task_type_parameters is None:
            task_type_parameters = []
        if sandboxes is None:
            sandboxes = []
        if info is None:
            info = ""

        self.task_type = task_type
        self.task_type_parameters = task_type_parameters
        self.shard = shard
        self.sandboxes = sandboxes
        self.info = info

    def export_to_dict(self):
        res = {
            'task_type': self.task_type,
            'task_type_parameters': self.task_type_parameters,
            'shard': self.shard,
            'sandboxes': self.sandboxes,
            'info': self.info,
            }
        return res

    @staticmethod
    def import_from_dict_with_type(data):
        type_ = data['type']
        del data['type']
        if type_ == 'compilation':
            return CompilationJob.import_from_dict(data)
        elif type_ == 'evaluation':
            return EvaluationJob.import_from_dict(data)
        else:
            raise Exception("Couldn't import dictionary with type %s" %
                            (type_))

    @classmethod
    def import_from_dict(cls, data):
        return cls(**data)


class CompilationJob(Job):
    """Job representing a compilation.

    Can represent either the compilation of a user test, or of a
    submission, or of an arbitrary source (as used in cmsMake).

    Input data (usually filled by ES): language, files, expected_files.
    Output data (filled by the Worker): success, compilation_success,
    files, text, plus.

    """

    def __init__(self, task_type=None, task_type_parameters=None,
                 shard=None, sandboxes=None, info=None, language=None,
                 files=None, expected_files=None, success=None,
                 compilation_success=None, text=None, plus=None):
        """Initialization.

        See base class for the remaining arguments.

        language (string|None): the language of the submission / user
            test.
        files ({string: File}|None): all the files the process will
            require.
        expected_files ({string: FileSchema}|None): the schemas of the
            files the process is expected to produce.
        success (bool|None): whether the job succeeded.
        compilation_success (bool|None): whether the compilation implicit
            in the job succeeded, or there was a compilation error.
        text ([object]|None): description of the outcome of the job,
            to be presented to the user. The first item is a string,
            potentially with %-escaping; the following items are the
            values to be %-formatted into the first.
        plus ({}|None): additional metadata.

        """
        if files is None:
            files = {}
        if expected_files is None:
            expected_files = {}

        Job.__init__(self, task_type, task_type_parameters,
                     shard, sandboxes, info)
        self.language = language
        self.files = files
        self.expected_files = expected_files
        self.success = success
        self.compilation_success = compilation_success
        self.text = text
        self.plus = plus

    def export_to_dict(self):
        res = Job.export_to_dict(self)
        res.update({
            'type': 'compilation',
            'language': self.language,
            'files': self.files,
            'expected_files': self.expected_files,
            'success': self.success,
            'compilation_success': self.compilation_success,
            'text': self.text,
            'plus': self.plus,
            })
        return res

    @classmethod
    def import_from_dict(cls, data):
        data['files'] = dict(
            (k, File(*v)) for k, v in data['files'].iteritems())
        data['expected_files'] = dict(
            (k, FileSchema(*v)) for k, v in data['expected_files'].iteritems())
        return cls(**data)


class EvaluationJob(Job):
    """Job representing an evaluation on a testcase.

    Can represent either the evaluation of a user test, or of a
    submission, or of an arbitrary source (as used in cmsMake).

    Input data (usually filled by ES): language, files, expected_files,
    time_limit, memory_limit. Output data (filled by the Worker):
    success, outcome, files, text, plus. Metadata: only_execution,
    get_output.

    """
    def __init__(self, task_type=None, task_type_parameters=None,
                 shard=None, sandboxes=None, info=None, language=None,
                 files=None, expected_files=None, time_limit=None,
                 memory_limit=None, success=None, outcome=None, text=None,
                 plus=None, only_execution=False, get_output=False):
        """Initialization.

        See base class for the remaining arguments.

        language (string|None): the language of the submission / user test.
        files ({string: File}|None): all the files the process will
            require.
        expected_files ({string: FileSchema}|None): the schemas of the
            files the process is expected to produce.
        time_limit (float|None): user time limit in seconds.
        memory_limit (int|None): memory limit in bytes.
        success (bool|None): whether the job succeeded.
        outcome (string|None): the outcome of the evaluation, from
            which to compute the score.
        text ([object]|None): description of the outcome of the job,
            to be presented to the user. The first item is a string,
            potentially with %-escaping; the following items are the
            values to be %-formatted into the first.
        plus ({}|None): additional metadata.
        only_execution (bool|None): whether to perform only the
            execution, or to compare the output with the reference
            solution too.
        get_output (bool|None): whether to retrieve the execution
            output (together with only_execution, useful for the user
            tests).

        """
        if files is None:
            files = {}
        if expected_files is None:
            expected_files = {}

        Job.__init__(self, task_type, task_type_parameters,
                     shard, sandboxes, info)
        self.language = language
        self.files = files
        self.expected_files = expected_files
        self.time_limit = time_limit
        self.memory_limit = memory_limit
        self.success = success
        self.outcome = outcome
        self.text = text
        self.plus = plus
        self.only_execution = only_execution
        self.get_output = get_output

    def export_to_dict(self):
        res = Job.export_to_dict(self)
        res.update({
            'type': 'evaluation',
            'language': self.language,
            'files': self.files,
            'expected_files': self.expected_files,
            'time_limit': self.time_limit,
            'memory_limit': self.memory_limit,
            'success': self.success,
            'outcome': self.outcome,
            'text': self.text,
            'plus': self.plus,
            'only_execution': self.only_execution,
            'get_output': self.get_output,
            })
        return res

    @classmethod
    def import_from_dict(cls, data):
        data['files'] = dict(
            (k, File(*v)) for k, v in data['files'].iteritems())
        data['expected_files'] = dict(
            (k, FileSchema(*v)) for k, v in data['expected_files'].iteritems())
        return cls(**data)


class JobGroup(object):
    """A collection of jobs.

    This is the minimal unit of action for a Worker.

    """

    def __init__(self, jobs=None, success=None):
        """Initialization.

        jobs ({string: Job}|None): the jobs composing the group, or
            None for no jobs.
        success (bool|None): whether all jobs succeded.

        """
        if jobs is None:
            jobs = {}

        self.jobs = jobs
        self.success = success

    def export_to_dict(self):
        res = {
            'jobs': dict((k, v.export_to_dict())
                         for k, v in self.jobs.iteritems()),
            'success': self.success,
            }
        return res

    @classmethod
    def import_from_dict(cls, data):
        data['jobs'] = dict(
            (k, Job.import_from_dict_with_type(v))
            for k, v in data['jobs'].iteritems())
        return cls(**data)

    # Compilation

    @staticmethod
    def prepare_compilation(submission, dataset):
        operation = "compilation of submission %d(%d)" % (submission.id,
                                                          dataset.id)

        task_type = get_task_type(dataset=dataset)

        # Verify language.
        if language not in task_type.supported_languages:
            logger.error("Language was not supported by TaskType %s when "
                         "preparing %s.", task_type.name, operation)
            raise ValueError("Language not supported.")

        job = CompilationJob()

        job.task_type = dataset.task_type
        job.task_type_parameters = dataset.task_type_parameters
        job.info = operation
        job.language = submission.language

        provided, expected = get_format_for_compilation(dataset, language, operation)
        job.files = get_files_for_compilation(provided, submission, dataset, operation)
        job.expected_files = expected

        jobs = {"": job}

        return JobGroup(jobs)

    def extract_compilation(self, sr):
        # This should actually be useless.
        sr.invalidate_compilation()

        job = self.jobs[""]
        assert isinstance(job, CompilationJob)

        # No need to check self.success or job.success because this
        # method gets called only if the first (and therefore the
        # second!) is True.

        sr.set_compilation_outcome(job.compilation_success)
        sr.compilation_text = json.dumps(job.text, encoding='utf-8')
        sr.compilation_stdout = job.plus.get('stdout')
        sr.compilation_stderr = job.plus.get('stderr')
        sr.compilation_time = job.plus.get('execution_time')
        sr.compilation_wall_clock_time = \
            job.plus.get('execution_wall_clock_time')
        sr.compilation_memory = job.plus.get('execution_memory')
        sr.compilation_shard = job.shard
        sr.compilation_sandbox = ":".join(job.sandboxes)

        # We're placing great trust in the TaskType by not verifying
        # the data we're storing. We should check the files against the
        # expected_files field more thoroughly (max_size & optional),
        # and maybe even generate that field from scratch to avoid
        # (accidental?) changes.
        for codename, schema in job.expected_files.iteritems():
            if codename in job.files:
                sr.compilation_files += [
                    CompilationFile(codename, job.files[codename].digest)]
            else:
                # XXX Should we do something? Make the Job fail? Print
                # a warning?
                pass

    # Evaluation

    @staticmethod
    def prepare_evaluation(submission, dataset):
        submission_result = submission.get_result(dataset)
        # This should have been created by now.
        assert submission_result is not None

        operation = "evaluation of submission %d(%d)" % (submission.id,
                                                         dataset.id)

        task_type = get_task_type(dataset=dataset)

        # Verify language.
        if submission.language not in task_type.supported_languages:
            logger.error("Language was not supported by TaskType %s when "
                         "preparing %s.", task_type.name, operation)
            raise ValueError("Language not supported.")

        # A template, containing the values common to all testcases.
        job = EvaluationJob()

        job.task_type = dataset.task_type
        job.task_type_parameters = dataset.task_type_parameters
        job.language = submission.language
        job.time_limit = dataset.time_limit
        job.memory_limit = dataset.memory_limit

        provided, expected = get_format_for_evaluation(dataset, language, operation)
        job.expected_files = expected

        # The actual Jobs, one for each testcase, indexed by codename.
        jobs = dict()

        for codename, testcase in dataset.testcases.iteritems():
            operation = "evaluation of submission %d(%d) on testcase %s" % \
                (submission.id, dataset.id, codename)

            job2 = deepcopy(job)

            job2.info = operation
            job2.files = get_files_for_evaluation(provided, submission, dataset, submission_result, testcase, operation)

            jobs[k] = job2

        return JobGroup(jobs)

    def extract_evaluation(self, sr):
        # This should actually be useless.
        sr.invalidate_evaluation()

        # No need to check self.success or job.success because this
        # method gets called only if the first (and therefore the
        # second!) is True.

        sr.set_evaluation_outcome()

        for codename, job in self.jobs.iteritems():
            assert isinstance(job, EvaluationJob)

            evaluation = Evaluation(
                outcome=job.outcome,
                text=json.dumps(job.text, encoding='utf-8'),
                execution_time=job.plus.get('execution_time'),
                execution_wall_clock_time=job.plus.get(
                    'execution_wall_clock_time'),
                execution_memory=job.plus.get('execution_memory'),
                evaluation_shard=job.shard,
                evaluation_sandbox=":".join(job.sandboxes),
                submission_result=sr,
                testcase=sr.dataset.testcases[codename])

            # We're placing great trust in the TaskType by not
            # verifying the data we're storing. We should check the
            # files against the expected_files field more thoroughly
            # (max_size & optional), and maybe even generate that field
            # from scratch to avoid (accidental?) changes.
            for codename, schema in job.expected_files.iteritems():
                if codename in job.files:
                    evaluation.evaluation_files += [
                        EvaluationFile(codename, job.files[codename].digest)]
                else:
                    # XXX Should we do something? Make the Job fail?
                    # Print a warning?
                    pass
