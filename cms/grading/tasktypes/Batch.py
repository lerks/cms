#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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
from __future__ import print_function
from __future__ import unicode_literals

import logging

from cms import LANGUAGES, LANGUAGE_TO_SOURCE_EXT_MAP, \
    LANGUAGE_TO_HEADER_EXT_MAP
from cms.grading import get_compilation_commands, get_evaluation_commands, \
    compilation_step, evaluation_step, human_evaluation_message, \
    is_evaluation_passed, extract_outcome_and_text, white_diff_step
from cms.grading.ParameterTypes import ParameterTypeCollection, \
    ParameterTypeChoice, ParameterTypeString, ParameterTypeBoolean
from cms.grading.TaskType import TaskType, \
    create_sandbox, delete_sandbox


logger = logging.getLogger(__name__)


# Dummy function to mark translatable string.
def N_(message):
    return message


class Batch(TaskType):
    """Task type class for a unique standalone submission source, with
    comparator (or not).

    Parameters needs to be a list of three elements.

    The first element is 'grader' or 'alone': in the first
    case, the source file is to be compiled with a provided piece of
    software ('grader'); in the other by itself.

    The second element is a 2-tuple of the input file name and output file
    name. The input file may be '' to denote stdin, and similarly the
    output filename may be '' to denote stdout.

    The third element is 'diff' or 'comparator' and says whether the
    output is compared with a simple diff algorithm or using a
    comparator.

    Note: the first element is used only in the compilation step; the
    others only in the evaluation step.

    A comparator can read argv[1], argv[2], argv[3] (respectively,
    input, correct output and user output) and should write the
    outcome to stdout and the text to stderr.

    """
    ALLOW_PARTIAL_SUBMISSION = False

    _COMPILATION = ParameterTypeChoice(
        "Compilation",
        "compilation",
        "",
        {"alone": "Submissions are self-sufficient",
         "grader": "Submissions are compiled with a grader"})

    _REDIRECT = ParameterTypeCollection(
        "Redirect I/O files to stdin/stdout",
        "redirect",
        "",
        [
            ParameterTypeBoolean("Input file", "input", False),
            ParameterTypeBoolean("Output file", "output", False),
        ])

    _EVALUATION = ParameterTypeChoice(
        "Evaluation",
        "evaluation",
        "",
        {"white_diff": "Outputs compared with white diff",
         "comparator": "Outputs are compared by a comparator"})

    ACCEPTED_PARAMETERS = [_COMPILATION, _REDIRECT, _EVALUATION]

    @property
    def name(self):
        """See TaskType.name."""
        # TODO add some details if a grader/comparator is used, etc...
        return "Batch"

    def get_compilation_commands(self, submission_format):
        """See TaskType.get_compilation_commands."""
        res = dict()
        for language in LANGUAGES:
            format_filename = submission_format[0]
            source_ext = LANGUAGE_TO_SOURCE_EXT_MAP[language]
            source_filenames = []
            # If a grader is specified, we add to the command line (and to
            # the files to get) the corresponding manager.
            if self.parameters[0] == "grader":
                source_filenames.append("grader%s" % source_ext)
            source_filenames.append(format_filename.replace(".%l", source_ext))
            executable_filename = format_filename.replace(".%l", "")
            commands = get_compilation_commands(language,
                                                source_filenames,
                                                executable_filename)
            res[language] = commands
        return res

    supported_languages = LANGUAGES

    user_file_format = \
        [UserFileSchema(
             lang, "source", "%(task)s" + SRC_MAP[lang], 102400, False)
         for lang in supported_languages]

    @property
    def dataset_file_format(self):
        result = []
        if self.parameters[0] == "grader":
            result += \
                [DatasetFileSchema(
                     lang, "grader", "grader" + SRC_MAP[lang], 102400, False)
                 for lang in self.supported_languages] + \
                [DatasetFileSchema(
                     lang, "header", "grader" + HDR_MAP[lang], 102400, True)
                 for lang in self.supported_languages]
        if self.parameters[2] == "comparator":
            result += \
                [DatasetFileSchema(
                     None, "checker", "checker", None, False)
        return result

    compilation_file_format = \
        [CompilationFileSchema(
             None, "executable", "%(task)s", None, False)]

    testcase_file_format = \
        [TestcaseFileSchema(
             None, "input", "input.txt", 5242880, False)] + \
        [TestcaseFileSchema(
             None, "result", "res.txt", None, False)]

    execution_file_format = \
        [ExecutionFileSchema(
             None, "input", "output.txt", 102400, False)]

    def get_user_managers(self, submission_format):
        """See TaskType.get_user_managers."""
        return []

    def get_auto_managers(self):
        """See TaskType.get_auto_managers."""
        return None

    def compile(self, job, file_cacher):
        """See TaskType.compile."""
        # The adherence of the submission files to the format published
        # by the TaskType has already been verified by CMS.

        # Create the sandbox
        sandbox = create_sandbox(file_cacher)
        job.sandboxes.append(sandbox.path)

        # Prepare the source files in the sandbox
        files = [job.files["source"]]
        # If a grader is specified we add it.
        if self.parameters[0] == "grader":
            files += [job.files["grader"]]
            if "header" in job.files:
                files += [job.files["header"]]

        for filename, digest in files:
            sandbox.create_file_from_storage(filename, digest)

        # Prepare the compilation command
        source_filenames = [filename for filename, digest in files]
        executable_filename = job.expected_files["executable"].filename
        commands = get_compilation_commands(job.language,
                                            source_filenames,
                                            executable_filename)

        # Run the compilation
        operation_success, compilation_success, text, plus = \
            compilation_step(sandbox, commands)

        # Retrieve the compiled executables
        job.success = operation_success
        job.compilation_success = compilation_success
        job.plus = plus
        job.text = text
        if operation_success and compilation_success:
            # FIXME Truncate?
            digest = sandbox.get_file_to_storage(
                executable_filename,
                "Executable %s for %s" % (executable_filename, job.info))
            job.files["executable"] = File(executable_filename, digest)

        # Cleanup
        delete_sandbox(sandbox)

    def evaluate(self, job, file_cacher):
        """See TaskType.evaluate."""
        # Create the sandbox
        sandbox = create_sandbox(file_cacher)

        # Prepare the execution
        executable = job.files["executable"]
        input_ = job.files["input"]
        output = job.expected_files["output"]

        # Prepare the evaluation command
        commands = get_evaluation_commands(job.language, executable.filename)

        stdin_redirect = None
        stdout_redirect = None
        if self.parameters[1][0]:
            stdin_redirect = input_.filename
        if self.parameters[1][1]:
            stdout_redirect = output.filename

        # Put the required files into the sandbox
        sandbox.create_file_from_storage(
            executable.filename, executable.digest, executable=True)
        sandbox.create_file_from_storage(input_.filename, input_.digest)

        # Actually performs the execution
        success, plus = evaluation_step(
            sandbox,
            commands,
            job.time_limit,
            job.memory_limit,
            stdin_redirect=stdin_redirect,
            stdout_redirect=stdout_redirect)

        job.sandboxes = [sandbox.path]
        job.plus = plus

        outcome = None
        text = None

        # Error in the sandbox: nothing to do!
        if not success:
            pass

        # Contestant's error: the marks won't be good
        elif not is_evaluation_passed(plus):
            outcome = 0.0
            text = human_evaluation_message(plus)
            # FIXME
            if job.get_output:
                job.user_output = None

        # Otherwise, advance to checking the solution
        else:

            # Check that the output file was created
            if not sandbox.file_exists(output.filename):
                outcome = 0.0
                text = [N_("Evaluation didn't produce file %s"),
                        output.filename]
                # FIXME
                if job.get_output:
                    job.user_output = None

            else:
                # If asked so, put the output file into the storage
                if job.get_output:
                    digest = sandbox.get_file_to_storage(
                        output.filename,
                        "Output file in job %s" % job.info,
                        trunc_len=output.max_size)
                    job.files["output"] = File(output.filename, digest)

                # If just asked to execute, fill text and set dummy
                # outcome.
                if job.only_execution:
                    outcome = 0.0
                    text = [N_("Execution completed successfully")]

                # Otherwise evaluate the output file.
                else:

                    # Put the reference solution into the sandbox
                    result = job.files["result"]
                    sandbox.create_file_from_storage(result.filename,
                                                     result.digest)

                    # Check the solution with white_diff
                    if self.parameters[2] == "white_diff":
                        outcome, text = white_diff_step(
                            sandbox, output.filename, result.filename)

                    # Check the solution with a comparator
                    elif self.parameters[2] == "comparator":
                        checker = job.files["checker"]
                        sandbox.create_file_from_storage(checker.filename,
                                                         checker.digest,
                                                         executable=True)

                        success, _ = evaluation_step(
                            sandbox,
                            [["./%s" % checker.filename, input_.filename,
                              result.filename, output.filename]])

                        if success:
                            try:
                                outcome, text = \
                                    extract_outcome_and_text(sandbox)
                            except ValueError, e:
                                logger.error("Invalid output from "
                                             "comparator: %s" % (e.message,),
                                             extra={"operation": job.info})
                                success = False

                    else:
                        raise ValueError("Unrecognized third parameter"
                                         " `%s' for Batch tasktype." %
                                         self.parameters[2])

        # Whatever happened, we conclude.
        job.success = success
        job.outcome = "%s" % outcome if outcome is not None else None
        job.text = text

        delete_sandbox(sandbox)
