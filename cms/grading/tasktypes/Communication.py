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
import tempfile
import shutil

from cms import config, logger
from cms.grading.Sandbox import wait_without_std
from cms.grading import get_compilation_command, compilation_step, \
    human_evaluation_message, is_evaluation_passed, \
    extract_outcome_and_text, evaluation_step_before_run, \
    evaluation_step_after_run
from cms.grading.TaskType import TaskType, \
    create_sandbox, delete_sandbox


class Communication(TaskType):
    """Task type class for tasks that requires:

    - a *manager* that reads the input file, work out the perfect
      solution on its own, and communicate the input (maybe with some
      modifications) on its standard output; it then reads the
      response of the user's solution from the standard input and
      write the outcome;

    - a *stub* that compiles with the user's source, reads from
      standard input what the manager says, and write back the user's
      solution to stdout.

    """
    ALLOW_PARTIAL_SUBMISSION = False

    name = "Communication"

    def get_compilation_command(self, language, files, managers):
        """See TaskType.get_compilation_command."""
        source_filenames = [files["source"], managers["stub"]]

        # XXX Dangerous heuristic!
        executable_filename = files["source"].partition('.')[0]

        return [" ".join(get_compilation_command(language,
                                                 source_filenames,
                                                 executable_filename))]

    def get_user_managers(self, submission_format):
        """See TaskType.get_user_managers."""
        return ["stub.%l"]

    def get_auto_managers(self):
        """See TaskType.get_auto_managers."""
        return ["manager"]

    def compile(self, job, file_cacher):
        """See TaskType.compile."""
        # Create the sandbox
        sandbox = create_sandbox(file_cacher)
        job.sandboxes = [sandbox.path]

        # Prepare the source files in the sandbox
        source_files = [job.files["source"]]
        if "stub" in job.managers:
            source_files += [job.managers["stub"]]
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
        # Create sandboxes and FIFOs
        sandbox_mgr = create_sandbox(file_cacher)
        sandbox_user = create_sandbox(file_cacher)
        job.sandboxes = [sandbox_user.path, sandbox_mgr.path]

        fifo_dir = tempfile.mkdtemp(dir=config.temp_dir)
        fifo_in = os.path.join(fifo_dir, "in")
        fifo_out = os.path.join(fifo_dir, "out")
        os.mkfifo(fifo_in)
        os.mkfifo(fifo_out)
        os.chmod(fifo_dir, 0o755)
        os.chmod(fifo_in, 0o666)
        os.chmod(fifo_out, 0o666)

        # First step: we start the manager.
        manager = job.managers["manager"]
        input_ = job.inputs["input"]

        sandbox_mgr.create_file_from_storage(
            manager.filename, manager.digest, executable=True)
        sandbox_mgr.create_file_from_storage(
            input_.filename, input_.digest)

        manager_command = [os.path.join(".", manager.filename),
                           fifo_in, fifo_out]

        manager = evaluation_step_before_run(
            sandbox_mgr,
            manager_command,
            job.time_limit,
            0,  # XXX Why not job.memory_limit?
            allow_dirs=[fifo_dir],
            stdin_redirect="input.txt")  # FIXME WTF input redirect?

        # Second step: we start the user submission compiled with the
        # stub.
        executable = job.executables["executable"]

        sandbox_user.create_file_from_storage(
            executable.filename, executable.digest, executable=True)

        command = [os.path.join(".", executable.filename),
                   fifo_out, fifo_in]

        process = evaluation_step_before_run(
            sandbox_user,
            command,
            job.time_limit,
            job.memory_limit,
            allow_dirs=[fifo_dir])

        # Consume output.
        wait_without_std([process, manager])
        # TODO: check exit codes with translate_box_exitcode.

        success_user, plus_user = \
            evaluation_step_after_run(sandbox_user)
        success_mgr, plus_mgr = \
            evaluation_step_after_run(sandbox_mgr)

        outcome = None
        text = None

        # If at least one evaluation had problems, we report the
        # problems.
        if not success_user or not success_mgr:
            success = False

        # If the user sandbox detected some problem (timeout, ...),
        # the outcome is 0.0 and the text describes that problem.
        elif not is_evaluation_passed(plus_user):
            success = True
            outcome, text = 0.0, human_evaluation_message(plus_user)

        # Otherwise, we use the manager to obtain the outcome.
        else:
            success = True
            outcome, text = extract_outcome_and_text(sandbox_mgr)

        # If asked so, save the output file, provided that it exists
        if job.get_output:
            if sandbox_mgr.file_exists("output.txt"):
                job.user_outputs["output"] = sandbox_mgr.get_file_to_storage(
                    "output.txt",
                    "Output file in job %s" % job.info)

        # Whatever happened, we conclude.
        job.success = success
        job.outcome = str(outcome) if outcome is not None else None
        job.text = text
        job.plus = plus_user

        delete_sandbox(sandbox_mgr)
        delete_sandbox(sandbox_user)
        shutil.rmtree(fifo_dir)
