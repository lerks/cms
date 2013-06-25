#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2013 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

import os

from cms import logger
from cms.grading import get_compilation_command, compilation_step, \
    evaluation_step, human_evaluation_message, is_evaluation_passed, \
    extract_outcome_and_text, white_diff_step
from cms.grading.ParameterTypes import ParameterTypeCollection, \
    ParameterTypeChoice, ParameterTypeBoolean
from cms.grading.TaskType import TaskType, \
    create_sandbox, delete_sandbox


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

    _REDIRECTION = ParameterTypeCollection(
        "Redirect I/O",
        "io",
        "",
        [
            ParameterTypeBoolean(
                "Redirect stdin to input file", "redirect_input", ""),
            ParameterTypeBoolean(
                "Redirect stdout to output file", "redirect_output", ""),
        ])

    _EVALUATION = ParameterTypeChoice(
        "Output evaluation",
        "evaluation",
        "",
        {"white_diff": "Outputs are compared with white diff",
         "comparator": "Outputs are compared by a comparator"})

    ACCEPTED_PARAMETERS = [_COMPILATION, _REDIRECTION, _EVALUATION]

    @property
    def name(self):
        """See TaskType.name."""
        # TODO add some details if a grader/comparator is used, etc...
        return "Batch"

    def get_compilation_command(self, language, files, managers):
        """See TaskType.get_compilation_command."""
        source_filenames = [files["source"]]
        if "grader" in managers:
            source_filenames += [managers["grader"]]
        # XXX should header be "task_name.h" or "grader.h"?
        # XXX should this if be nested?
        if "grader_h" in managers:
            source_filenames += [managers["grader_h"]]

        # XXX Dangerous heuristic!
        executable_filename = files["source"].partition('.')[0]

        return [" ".join(get_compilation_command(language,
                                                 source_filenames,
                                                 executable_filename))]

    def get_user_managers(self, submission_format):
        """See TaskType.get_user_managers."""
        return []

    def get_auto_managers(self):
        """See TaskType.get_auto_managers."""
        return None

    def compile(self, job, file_cacher):
        """See TaskType.compile."""
        # Create the sandbox
        sandbox = create_sandbox(file_cacher)
        job.sandboxes = [sandbox.path]

        # Prepare the source files in the sandbox
        source_files = [job.files["source"]]
        if "grader" in job.managers:
            source_files += [job.managers["grader"]]
        if "header" in job.managers:
            source_files += [job.managers["header"]]

        for filename, digest in source_files:
            sandbox.create_file_from_storage(filename, digest)

        # Determine the executable filename
        # XXX Dangerous heuristic!
        executable_filename = job.files["source"].filename.partition('.')[0]

        # Prepare the compilation command
        command = get_compilation_command(job.language,
                                          [f.filename for f in source_files],
                                          executable_filename)

        # Run the compilation
        operation_success, compilation_success, text, plus = \
            compilation_step(sandbox, command)

        # Retrieve the compiled executables
        job.success = operation_success
        job.compilation_success = compilation_success
        job.plus = plus
        job.text = text

        if operation_success and compilation_success:
            digest = sandbox.get_file_to_storage(
                executable_filename,
                "Executable %s for %s" % (executable_filename, job.info))
            job.executables["executable"] = File(executable_filename, digest)

        # Cleanup
        delete_sandbox(sandbox)

    def evaluate(self, job, file_cacher):
        """See TaskType.evaluate."""
        # Create the sandbox
        sandbox = create_sandbox(file_cacher)
        job.sandboxes = [sandbox.path]

        # Obtain the required files
        executable = job.executables["executable"]
        input_ = job.inputs["input"]
        output = job.outputs["output"]

        # Put the required files into the sandbox
        sandbox.create_file_from_storage(
            executable.filename, executable.digest, executable=True)
        sandbox.create_file_from_storage(
            input_.filename, input_.digest)

        # Prepare the execution
        command = [os.path.join(".", executable.filename)]

        stdin_redirect = None
        stdout_redirect = None
        if self.parameters[0]:
            stdin_redirect = input_.filename
        if self.parameters[1]:
            stdout_redirect = output.filename

        # Actually perform the execution
        success, plus = evaluation_step(
            sandbox,
            command,
            job.time_limit,
            job.memory_limit,
            stdin_redirect=stdin_redirect,
            stdout_redirect=stdout_redirect)

        outcome = None
        text = None

        # Error in the sandbox: nothing to do!
        if not success:
            pass

        # Contestant's error: the marks won't be good
        elif not is_evaluation_passed(plus):
            outcome = 0.0
            text = human_evaluation_message(plus)

        # Otherwise, advance to checking the solution
        else:

            # Check that the output file was created
            if not sandbox.file_exists(output.filename):
                outcome = 0.0
                text = "Execution didn't produce file %s" % output.filename

            else:
                # If asked so, put the output file into the storage
                if job.get_output:
                    job.user_outputs["output"] = sandbox.get_file_to_storage(
                        output.filename,
                        "Output file in job %s" % job.info,
                        trunc_len=100 * 1024)

                # If not asked otherwise, evaluate the output file
                if not job.only_execution:

                    # Put the reference solution into the sandbox
                    sandbox.create_file_from_storage(
                        "res.txt",
                        output.digest)

                    # Check the solution with white_diff
                    if "checker" not in job.managers:
                        outcome, text = white_diff_step(
                            sandbox, output.filename, "res.txt")

                    # Check the solution with a comparator
                    else:
                        checker = job.managers["checker"]

                        sandbox.create_file_from_storage(
                            checker.filename, checker.digest, executable=True)
                        success, _ = evaluation_step(
                            sandbox,
                            ["./%s" % checker.filename,
                             input_.filename, "res.txt", output.filename])

                        if success:
                            try:
                                outcome, text = \
                                    extract_outcome_and_text(sandbox)
                            except ValueError, e:
                                logger.error("Invalid output from "
                                             "comparator: %s" % (e.message,))
                                success = False

        # Whatever happened, we conclude.
        job.success = success
        job.outcome = str(outcome) if outcome is not None else None
        job.text = text
        job.plus = plus

        delete_sandbox(sandbox)
