#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2013 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2013 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
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

"""Task-related database interface for SQLAlchemy. Not to be used
directly (import it from SQLAlchemyAll).

"""

from datetime import timedelta

from sqlalchemy.schema import Column, ForeignKey, CheckConstraint, \
    UniqueConstraint, ForeignKeyConstraint
from sqlalchemy.types import Boolean, Integer, Float, String, Interval
from sqlalchemy.orm import relationship, backref
from sqlalchemy.orm.collections import attribute_mapped_collection
from sqlalchemy.ext.orderinglist import ordering_list

from cms.db.SQLAlchemyUtils import Base
from cms.db.Contest import Contest
from cms.db.SmartMappedCollection import smart_mapped_collection


class Task(Base):
    """Class to store a task. Not to be used directly (import it from
    SQLAlchemyAll).

    """
    __tablename__ = 'tasks'
    __table_args__ = (
        UniqueConstraint('contest_id', 'num'),
        UniqueConstraint('contest_id', 'name'),
        ForeignKeyConstraint(
            ("id", "active_dataset_id"),
            ("datasets.task_id", "datasets.id"),
            onupdate="SET NULL", ondelete="SET NULL",
            # Use an ALTER query to set this foreign key after
            # both tables have been CREATEd, to avoid circular
            # dependencies.
            use_alter=True,
            name="fk_active_dataset_id"
        ),
        CheckConstraint("token_initial <= token_max"),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True,
        # Needed to enable autoincrement on integer primary keys that
        # are referenced by a foreign key defined on this table.
        autoincrement='ignore_fk')

    # Number of the task for sorting.
    num = Column(
        Integer,
        nullable=False)

    # Contest (id and object) owning the task.
    contest_id = Column(
        Integer,
        ForeignKey(Contest.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    contest = relationship(
        Contest,
        backref=backref('tasks',
                        collection_class=ordering_list('num'),
                        order_by=[num],
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Short name and long human readable title of the task.
    name = Column(
        String,
        nullable=False)
    title = Column(
        String,
        nullable=False)

    # A JSON-encoded lists of strings: the language codes of the
    # statements that will be highlighted to all users for this task.
    primary_statements = Column(
        String,
        nullable=False,
        default="[]")

    # Parameter to define the token behaviour. See Contest.py for
    # details. The only change is that these parameters influence the
    # contest in a task-per-task behaviour. To play a token on a given
    # task, a user must satisfy the condition of the contest and the
    # one of the task.
    token_initial = Column(
        Integer,
        CheckConstraint("token_initial >= 0"),
        nullable=True)
    token_max = Column(
        Integer,
        CheckConstraint("token_max > 0"),
        nullable=True)
    token_total = Column(
        Integer,
        CheckConstraint("token_total > 0"),
        nullable=True)
    token_min_interval = Column(
        Interval,
        CheckConstraint("token_min_interval >= '0 seconds'"),
        nullable=False,
        default=timedelta())
    token_gen_time = Column(
        Interval,
        CheckConstraint("token_gen_time >= '0 seconds'"),
        nullable=False,
        default=timedelta())
    token_gen_number = Column(
        Integer,
        CheckConstraint("token_gen_number >= 0"),
        nullable=False,
        default=0)

    # Maximum number of submissions or user_tests allowed for each user
    # on this task during the whole contest or None to not enforce
    # this limitation.
    max_submission_number = Column(
        Integer,
        CheckConstraint("max_submission_number > 0"),
        nullable=True)
    max_user_test_number = Column(
        Integer,
        CheckConstraint("max_user_test_number > 0"),
        nullable=True)

    # Minimum interval between two submissions or user_tests for this
    # task, or None to not enforce this limitation.
    min_submission_interval = Column(
        Interval,
        CheckConstraint("min_submission_interval > '0 seconds'"),
        nullable=True)
    min_user_test_interval = Column(
        Interval,
        CheckConstraint("min_user_test_interval > '0 seconds'"),
        nullable=True)

    # The scores for this task will be rounded to this number of
    # decimal places.
    score_precision = Column(
        Integer,
        CheckConstraint("score_precision >= 0"),
        nullable=False,
        default=0)

    # Active Dataset (id and object) currently being used for scoring.
    # The ForeignKeyConstraint for this column is set at table-level.
    active_dataset_id = Column(
        Integer,
        nullable=True)
    active_dataset = relationship(
        'Dataset',
        foreign_keys=[active_dataset_id],
        # XXX In SQLAlchemy 0.8 we could remove this:
        primaryjoin='Task.active_dataset_id == Dataset.id',
        # Use an UPDATE query *after* an INSERT query (and *before* a
        # DELETE query) to set (and unset) the column associated to
        # this relationship.
        post_update=True)

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # datasets (list of Dataset objects)
    # statements (dict of Statement objects indexed by language code)
    # attachments (dict of Attachment objects indexed by filename)
    # file_schemas (list of FileSchema objects)
    # manager_schemas (list of ManagerSchema objects)
    # input_schemas (dict of InputSchema objects indexed by codename)
    # output_schemas (dict of OutputSchema objects indexed by codename)
    # submissions (list of Submission objects)
    # user_tests (list of UserTest objects)

    def get_file_schemas(self, lang=None):
        result = dict()

        # Fill with the language-independent files first.
        for s in self.file_schemas:
            if s.language is None:
                result[s.codename] = s

        if lang is not None:
            # Fill with language-specific files, overwriting the
            # previous ones if needed.
            for s in self.file_schemas:
                if s.language == lang:
                    result[s.codename] = s

        return result

    def get_manager_schemas(self, lang=None):
        result = dict()

        # Fill with the language-independent files first.
        for s in self.manager_schemas:
            if s.language is None:
                result[s.codename] = s

        if lang is not None:
            # Fill with language-specific files, overwriting the
            # previous ones if needed.
            for s in self.manager_schemas:
                if s.language == lang:
                    result[s.codename] = s

        return result


class Statement(Base):
    """Class to store a translation of the task statement. Not
    to be used directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'statements'
    __table_args__ = (
        UniqueConstraint('task_id', 'language'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Task (id and object) the statement is for.
    task_id = Column(
        Integer,
        ForeignKey(Task.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    task = relationship(
        Task,
        backref=backref('statements',
                        collection_class=smart_mapped_collection('language'),
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Code for the language the statement is written in.
    # It can be an arbitrary string, but if it's in the form "en" or "en_US"
    # it will be rendered appropriately on the interface (i.e. "English" and
    # "English (United States of America)"). These codes need to be taken from
    # ISO 639-1 and ISO 3166-1 respectively.
    language = Column(
        String,
        nullable=False)

    # Digest of the file.
    digest = Column(
        String,
        nullable=False)


class Attachment(Base):
    """Class to store additional files to give to the user together
    with the statement of the task. Not to be used directly (import it
    from SQLAlchemyAll).

    """
    __tablename__ = 'attachments'
    __table_args__ = (
        UniqueConstraint('task_id', 'filename'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Task (id and object) owning the attachment.
    task_id = Column(
        Integer,
        ForeignKey(Task.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    task = relationship(
        Task,
        backref=backref('attachments',
                        collection_class=smart_mapped_collection('filename'),
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Filename and digest of the provided attachment.
    filename = Column(
        String,
        nullable=False)
    digest = Column(
        String,
        nullable=False)


class FileSchema(Base):
    """Definition of a source file used in the judging process.

    Source files are what contestants are supposed to produce during
    the contest. They're mostly written in a programming language and
    are intended to be (compiled and) executed, but this isn't always
    the case (in output-only tasks the "source files" are actually
    plain-text output files produced by a previous computation).

    All files the user is required to provide in a submission have to
    be of this type; usertests, on the other hand, can require other
    file types to be submitted too.

    The main purpose of this class is to map the language-independent
    "roles" that need to act during the judging process with the actual
    language-specific filenames that will "play" them.
    This is used both when putting and getting files in to and out from
    the sandbox and when handling the files that the user is submitting
    (i.e. give hints for, validate and parse the submitted files).

    Not to be used directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'file_schemas'
    __table_args__ = (
        UniqueConstraint('task_id', 'codename', 'language'),
        UniqueConstraint('task_id', 'filename', 'language'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Task (id and object) owning the file schema.
    task_id = Column(
        Integer,
        ForeignKey(Task.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    task = relationship(
        Task,
        backref=backref('file_schemas',
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # The name that the TaskType uses to identify this file. Common
    # examples are "source", "encoder", "decoder", etc. It should
    # describe the role of the file in the judging process and it has
    # to be language-independent.
    codename = Column(
        String,
        nullable=False)

    # The filename that both the contestant and the administrator use
    # when dealing with this file (in the task statement, in their
    # source code, etc.). This name will be suggested by CWS when
    # prompting the user to submit files, used when parsing the
    # submitted files to detect their codenames and the language of the
    # whole submission, used by TaskTypes when putting files in to the
    # sandbox, etc. This name has to be language-specific and cannot
    # contain wildcards (like "%l").
    filename = Column(
        String,
        nullable=False)

    # The programming language this file is supposed to be written in,
    # or None if not applicable (for example in an output-only task).
    # This value should be the codename of one of the supported
    # languages, i.e. one of the elements of cms.LANGUAGES.
    language = Column(
        String,
        nullable=True)

    # A not-too-long human readable description to tell contestants
    # what we expect this file to contain. It's mainly used in the
    # submission form of CWS.
    description = Column(
        String,
        nullable=False)

    # The maximum size, in bytes, we allow the files submitted by users
    # to be.
    max_size = Column(
        Integer,
        CheckConstraint("max_size >= 0"),
        nullable=False)


class ManagerSchema(Base):
    """Definition of a manager used in the judging process.

    Managers are subsidiary utilities needed to perform the judging
    process. They're provided by the administrators, but for usertests
    the users can be allowed to provide their own implementations. The
    most common use-cases are:
    - "graders" (or "stubs") are compiled together with a user-provided
      source file to implement the main function, the input parsing and
      the output formatting;
    - "managers" are independently-compiled programs that interact with
      the user's program using appropriate communication channels (e.g.
      pipes) providing data, making queries and checking results, in
      order to prevent the user to access input data before it's
      supposed to do it;
    - "checkers" are tools that verify the correctness of the produced
      output.

    The user is allowed to submit files of this type only when making
    an usertest, and only if the administrator decides to allow it (by
    not providing its own implementation).

    The main purpose of this class is to map the language-independent
    "roles" that need to act during the judging process with the actual
    language-specific filenames that will "play" them.
    This is used both when putting and getting files in to and out from
    the sandbox and when handling the files that the user is submitting
    (i.e. give hints for, validate and parse the submitted files).

    Not to be used directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'manager_schemas'
    __table_args__ = (
        UniqueConstraint('task_id', 'codename', 'language'),
        UniqueConstraint('task_id', 'filename', 'language'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Task (id and object) owning the manager schema.
    task_id = Column(
        Integer,
        ForeignKey(Task.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    task = relationship(
        Task,
        backref=backref('manager_schemas',
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # The name that the TaskType uses to identify this file. Common
    # examples are "grader", "manager", "checker", etc. It should
    # describe the role of the file in the judging process and it has
    # to be language-independent.
    codename = Column(
        String,
        nullable=False)

    # The filename that both the contestant and the administrator use
    # when dealing with this file (in the task statement, in their
    # source code, etc.). This name will be suggested by CWS when
    # prompting the user to submit files, used when parsing the
    # submitted files to detect their codenames and the language of the
    # whole submission, used by TaskTypes when putting files in to the
    # sandbox, etc. This name has to be language-specific and cannot
    # contain wildcards (like "%l").
    filename = Column(
        String,
        nullable=False)

    # The programming language this file is supposed to be written in,
    # or None if not applicable (for example a plain-text file with a
    # large dictionary of words to be used in a text-processing task).
    # This value should be the codename of one of the supported
    # languages, i.e. one of the elements of cms.LANGUAGES.
    language = Column(
        String,
        nullable=True)

    # A not-too-long human readable description to tell contestants
    # what we expect this file to contain. It's mainly used in the
    # submission form of CWS.
    description = Column(
        String,
        nullable=False)

    # The maximum size, in bytes, we allow the files submitted by users
    # to be.
    max_size = Column(
        Integer,
        CheckConstraint("max_size >= 0"),
        nullable=False)


class InputSchema(Base):
    """Definition of an input file used in the judging process.

    Input files contain the data that the user's program has to
    elaborate to prove that it can solve the task correctly and
    efficiently. Inputs, and their corresponding outputs, are what
    defines a testcase, which in turn is an "instance" of the task.
    They play a role in the evaluation stage of the judging process
    (but not during compilation), and they're simply made available
    for the contestant's program to read.

    The user is allowed to submit files of this type only when making
    an usertest.

    The main purpose of this class is to map the language-independent
    "roles" that need to act during the judging process with the actual
    language-specific filenames that will "play" them.
    This is used both when putting and getting files in to and out from
    the sandbox and when handling the files that the user is submitting
    (i.e. give hints for, validate and parse the submitted files).

    Not to be used directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'input_schemas'
    __table_args__ = (
        UniqueConstraint('task_id', 'codename'),
        UniqueConstraint('task_id', 'filename'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Task (id and object) owning the input schema.
    task_id = Column(
        Integer,
        ForeignKey(Task.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    task = relationship(
        Task,
        backref=backref('input_schemas',
                        collection_class=smart_mapped_collection('codename'),
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # The name that the TaskType uses to identify this file. The most
    # common example is just "input", and only in rare occasions will
    # there be the need for something more than this. It should
    # describe the role of the file in the judging process.
    codename = Column(
        String,
        nullable=False)

    # The filename that both the contestant and the administrator use
    # when dealing with this file (in the task statement, in their
    # source code, etc.). This name will be suggested by CWS when
    # prompting the user to submit files, used when parsing the
    # submitted files to detect their codenames, used by TaskTypes when
    # putting files in to the sandbox, etc.
    filename = Column(
        String,
        nullable=False)

    # A not-too-long human readable description to tell contestants
    # what we expect this file to contain. It's mainly used in the
    # submission form of CWS.
    description = Column(
        String,
        nullable=False)

    # The maximum size, in bytes, we allow the files submitted by users
    # to be.
    max_size = Column(
        Integer,
        CheckConstraint("max_size >= 0"),
        nullable=False)


class OutputSchema(Base):
    """Definition of an output file used in the judging process.

    Output files are the results that a program has produced from an
    input file. They contain the "answer" that we will read, parse,
    validate and compare with the official result to verify its
    correctness. From them we will derive an outcome and a text that
    ScoreTypes will use to assign a score to the submission.

    The user is never allowed to submit files of this type.

    The main purpose of this class is to map the language-independent
    "roles" that need to act during the judging process with the actual
    language-specific filenames that will "play" them.
    This is used both when putting and getting files in to and out from
    the sandbox and when presenting the results of an usertest (i.e.
    the outputs produced by the execution) to the user.

    Not to be used directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'output_schemas'
    __table_args__ = (
        UniqueConstraint('task_id', 'codename'),
        UniqueConstraint('task_id', 'filename'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Task (id and object) owning the output schema.
    task_id = Column(
        Integer,
        ForeignKey(Task.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    task = relationship(
        Task,
        backref=backref('output_schemas',
                        collection_class=smart_mapped_collection('codename'),
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # The name that the TaskType uses to identify this file. The most
    # common example is just "output", and only in rare occasions will
    # there be the need for something more than this. It should
    # describe the role of the file in the judging process.
    codename = Column(
        String,
        nullable=False)

    # The filename that both the contestant and the administrator use
    # when dealing with this file (in the task statement, in their
    # source code, etc.). This name will be used by TaskTypes when
    # getting and putting files out of an in to the sandbox, etc.
    filename = Column(
        String,
        nullable=False)


class Dataset(Base):
    """Class to store the information about a data set. Not to be used
    directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'datasets'
    __table_args__ = (
        UniqueConstraint('task_id', 'description'),
        # Useless, in theory, because 'id' is already unique. Yet, we
        # need this because it's a target of a foreign key.
        UniqueConstraint('id', 'task_id'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Task (id and object) owning the dataset.
    task_id = Column(
        Integer,
        ForeignKey(Task.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False)
    task = relationship(
        Task,
        foreign_keys=[task_id],
        # XXX In SQLAlchemy 0.8 we could remove this:
        primaryjoin='Task.id == Dataset.task_id',
        backref=backref('datasets',
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # A human-readable text describing the dataset.
    description = Column(
        String,
        nullable=False)

    # Whether this dataset will be automatically judged by ES and SS
    # "in background", together with the active dataset of each task.
    autojudge = Column(
        Boolean,
        nullable=False,
        default=False)

    # Time and memory limits for every testcase.
    time_limit = Column(
        Float,
        nullable=True)
    memory_limit = Column(
        Integer,
        nullable=True)

    # Name of the TaskType child class suited for the task.
    task_type = Column(
        String,
        nullable=False)

    # Parameters for the task type class, JSON encoded.
    task_type_parameters = Column(
        String,
        nullable=False)

    # Name of the ScoreType child class suited for the task.
    score_type = Column(
        String,
        nullable=False)

    # Parameters for the score type class, JSON encoded.
    score_type_parameters = Column(
        String,
        nullable=False)

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # managers (list of Manager objects)
    # testcases (dict of Testcase objects indexed by codename)

    def get_managers(self, lang=None):
        result = dict()

        # Fill with the language-independent files first.
        for m in self.managers:
            if m.language is None:
                result[m.codename] = m

        if lang is not None:
            # Fill with language-specific files, overwriting the
            # previous ones if needed.
            for m in self.managers:
                if m.language == lang:
                    result[m.codename] = m

        return result


class Manager(Base):
    """An actual manager file, an "instance" of a ManagerSchema.

    See the documentation for ManagerSchema.

    Not to be used directly (import it from SQLAlchemyAll).


    """
    __tablename__ = 'managers'
    __table_args__ = (
        UniqueConstraint('dataset_id', 'schema_id'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Dataset (id and object) owning the manager.
    dataset_id = Column(
        Integer,
        ForeignKey(Dataset.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    dataset = relationship(
        Dataset,
        backref=backref('managers',
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Schema (id and object) this manager is an instance of.
    schema_id = Column(
        Integer,
        ForeignKey(ManagerSchema.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    schema = relationship(
        ManagerSchema)

    # Digest of the provided manager.
    digest = Column(
        String,
        nullable=False)

    @property
    def codename(self):
        return self.schema.codename

    @property
    def filename(self):
        return self.schema.filename

    @property
    def language(self):
        return self.schema.language


class Testcase(Base):
    """Class to store the information about a testcase. Not to be used
    directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'testcases'
    __table_args__ = (
        UniqueConstraint('dataset_id', 'codename'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Dataset (id and object) owning the testcase.
    dataset_id = Column(
        Integer,
        ForeignKey(Dataset.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    dataset = relationship(
        Dataset,
        backref=backref('testcases',
                        collection_class=smart_mapped_collection('codename'),
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Codename identifying the testcase.
    codename = Column(
        String,
        nullable=False)

    # If the testcase outcome is going to be showed to the user (even
    # without playing a token).
    public = Column(
        Boolean,
        nullable=False,
        default=False)

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # inputs (dict of Input objects indexed by codename)
    # outputs (dict of Output objects indexed by codename)


class Input(Base):
    """An actual input file, an "instance" of an InputSchema.

    See the documentation for InputSchema.

    Not to be used directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'inputs'
    __table_args__ = (
        UniqueConstraint('testcase_id', 'schema_id'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Testcase (id and object) owning the input.
    testcase_id = Column(
        Integer,
        ForeignKey(Testcase.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    testcase = relationship(
        Testcase,
        backref=backref('inputs',
                        collection_class=attribute_mapped_collection('codename'),
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Schema (id and object) this input is an instance of.
    schema_id = Column(
        Integer,
        ForeignKey(InputSchema.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    schema = relationship(
        InputSchema)

    # Digest of the provided input.
    digest = Column(
        String,
        nullable=False)

    @property
    def codename(self):
        return self.schema.codename

    @property
    def filename(self):
        return self.schema.filename


class Output(Base):
    """An actual output file, an "instance" of an OutputSchema.

    See the documentation for OutputSchema.

    Not to be used directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'outputs'
    __table_args__ = (
        UniqueConstraint('testcase_id', 'schema_id'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Testcase (id and object) owning the output.
    testcase_id = Column(
        Integer,
        ForeignKey(Testcase.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    testcase = relationship(
        Testcase,
        backref=backref('outputs',
                        collection_class=attribute_mapped_collection('codename'),
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Schema (id and object) this output is an instance of.
    schema_id = Column(
        Integer,
        ForeignKey(OutputSchema.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    schema = relationship(
        OutputSchema)

    # Digest of the provided output.
    digest = Column(
        String,
        nullable=False)

    @property
    def codename(self):
        return self.schema.codename

    @property
    def filename(self):
        return self.schema.filename
