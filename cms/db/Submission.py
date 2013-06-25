#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
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

"""Submission-related database interface for SQLAlchemy. Not to be
used directly (import  from SQLAlchemyAll).

"""

from sqlalchemy.schema import Column, ForeignKey, ForeignKeyConstraint, \
    UniqueConstraint
from sqlalchemy.types import Integer, Float, String, DateTime
from sqlalchemy.orm import relationship, backref
from sqlalchemy.orm.collections import attribute_mapped_collection

from cms.db.SQLAlchemyUtils import Base
from cms.db.Task import Task, Dataset, Testcase
from cms.db.User import User
from cms.db.SmartMappedCollection import smart_mapped_collection

from cmscommon.DateTime import make_datetime, make_timestamp


class Submission(Base):
    """Class to store a submission. Not to be used directly (import it
    from SQLAlchemyAll).

    """
    __tablename__ = 'submissions'

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # User (id and object) that did the submission.
    user_id = Column(
        Integer,
        ForeignKey(User.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    user = relationship(
        User,
        backref=backref("submissions",
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Task (id and object) of the submission.
    task_id = Column(
        Integer,
        ForeignKey(Task.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    task = relationship(
        Task,
        backref=backref("submissions",
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Time of the submission.
    timestamp = Column(
        DateTime,
        nullable=False)

    # Language of submission, or None if not applicable.
    language = Column(
        String,
        nullable=True)

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # token (Token object or None)
    # results (list of SubmissionResult objects)

    def get_result(self, dataset):
        # Use IDs to avoid triggering a lazy-load query.
        assert self.task_id == dataset.task_id

        return SubmissionResult.get_from_id(
            (self.id, dataset.id), self.sa_session)

    def get_result_or_create(self, dataset):
        submission_result = self.get_result(dataset)

        if submission_result is None:
            submission_result = SubmissionResult(submission=self,
                                                 dataset=dataset)

        return submission_result

    def tokened(self):
        """Return if the user played a token against the submission.

        return (bool): True if tokened, False otherwise.

        """
        return self.token is not None


class File(Base):
    """Class to store information about one file submitted within a
    submission. Not to be used directly (import it from
    SQLAlchemyAll).

    """
    __tablename__ = 'files'
    __table_args__ = (
        UniqueConstraint('submission_id', 'filename'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Submission (id and object) owning the file.
    submission_id = Column(
        Integer,
        ForeignKey(Submission.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    submission = relationship(
        Submission,
        backref=backref('files',
                        collection_class=smart_mapped_collection('filename'),
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Filename and digest of the submitted file.
    filename = Column(
        String,
        nullable=False)
    digest = Column(
        String,
        nullable=False)


class Token(Base):
    """Class to store information about a token. Not to be used
    directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'tokens'
    __table_args__ = (
        UniqueConstraint('submission_id'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Submission (id and object) the token has been used on.
    submission_id = Column(
        Integer,
        ForeignKey(Submission.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    submission = relationship(
        Submission,
        backref=backref(
            "token",
            uselist=False,
            cascade="all, delete-orphan",
            passive_deletes=True),
        single_parent=True)

    # Time the token was played.
    timestamp = Column(
        DateTime,
        nullable=False,
        default=make_datetime)


class SubmissionResult(Base):
    """Class to store the evaluation results of a submission. Not to
    be used directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'submission_results'
    __table_args__ = (
        UniqueConstraint('submission_id', 'dataset_id'),
    )

    # Primary key is (submission_id, dataset_id).
    submission_id = Column(
        Integer,
        ForeignKey(Submission.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True)
    submission = relationship(
        Submission,
        backref=backref(
            "results",
            cascade="all, delete-orphan",
            passive_deletes=True))

    dataset_id = Column(
        Integer,
        ForeignKey(Dataset.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True)
    dataset = relationship(
        Dataset)

    # Now below follow the actual result fields.

    # Compilation outcome (can be None = yet to compile, "ok" =
    # compilation successful and we can evaluate, "fail" =
    # compilation unsuccessful, throw it away).
    compilation_outcome = Column(
        String,
        nullable=True)

    # String containing output from the sandbox, and the compiler
    # stdout and stderr.
    compilation_text = Column(
        String,
        nullable=True)

    # Number of attempts of compilation.
    compilation_tries = Column(
        Integer,
        nullable=False,
        default=0)

    # Worker shard and sandbox where the compilation was performed.
    compilation_shard = Column(
        Integer,
        nullable=True)
    compilation_sandbox = Column(
        String,
        nullable=True)

    # Evaluation outcome (can be None = yet to evaluate, "ok" =
    # evaluation successful). At any time, this should be equal to
    # evaluations != [].
    evaluation_outcome = Column(
        String,
        nullable=True)

    # Number of attempts of evaluation.
    evaluation_tries = Column(
        Integer,
        nullable=False,
        default=0)

    # Score as computed by ScoringService. Null means not yet scored.
    score = Column(
        Float,
        nullable=True)

    # Score details. It's a JSON-encoded string containing information
    # that is given to ScoreType.get_html_details to generate an HTML
    # snippet that is shown on AWS and, if the user used a token, on
    # CWS to display the details of the submission.
    # For example, results for each testcases, subtask, etc.
    score_details = Column(
        String,
        nullable=True)

    # The same as the last two fields, but from the point of view of
    # the user (when he/she did not play a token).
    public_score = Column(
        Float,
        nullable=True)
    public_score_details = Column(
        String,
        nullable=True)

    # Ranking score details. It is a list of strings that are going to
    # be shown in a single row in the table of submission in RWS. JSON
    # encoded.
    ranking_score_details = Column(
        String,
        nullable=True)

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # executables (dict of Executable objects indexed by filename)
    # evaluations (list of Evaluation objects)

    def get_evaluation(self, testcase):
        """Return the Evaluation of this SR on the given Testcase, if any

        testcase (Testcase): the testcase the returned evaluation will
                             belong to
        return (Evaluation): the (only!) evaluation of this submission
                             result on the given testcase, or None if
                             there isn't any.

        """
        # Use IDs to avoid triggering a lazy-load query.
        assert self.dataset_id == testcase.dataset_id

        # XXX If self.evaluations is already loaded we can walk over it
        # and spare a query.
        # (We could use .one() and avoid a LIMIT but we would need to
        # catch a NoResultFound exception.)
        self.sa_session.query(Evaluation)\
            .filter(Evaluation.submission_result == self)\
            .filter(Evaluation.testcase == testcase)\
            .first()

    def compiled(self):
        """Return if the submission has been compiled.

        return (bool): True if compiled, False otherwise.

        """
        return self.compilation_outcome is not None

    def evaluated(self):
        """Return if the submission has been evaluated.

        return (bool): True if evaluated, False otherwise.

        """
        return self.evaluation_outcome is not None

    def scored(self):
        """Return if the submission has been scored.

        return (bool): True if scored, False otherwise.

        """
        return self.score is not None

    def invalidate_compilation(self):
        """Blank all compilation and evaluation outcomes, and the score.

        """
        self.invalidate_evaluation()
        self.compilation_outcome = None
        self.compilation_text = None
        self.compilation_tries = 0
        self.compilation_shard = None
        self.compilation_sandbox = None
        self.executables = {}

    def invalidate_evaluation(self):
        """Blank the evaluation outcomes and the score.

        """
        self.invalidate_score()
        self.evaluation_outcome = None
        self.evaluation_tries = 0
        self.evaluations = []

    def invalidate_score(self):
        """Blank the score.

        """
        self.score = None
        self.score_details = None
        self.public_score = None
        self.public_score_details = None
        self.ranking_score_details = None


class Executable(Base):
    """Class to store information about one file generated by the
    compilation of a submission. Not to be used directly (import it
    from SQLAlchemyAll).

    """
    __tablename__ = 'executables'
    __table_args__ = (
        ForeignKeyConstraint(
            ('submission_id', 'dataset_id'),
            (SubmissionResult.submission_id, SubmissionResult.dataset_id),
            onupdate="CASCADE", ondelete="CASCADE"),
        UniqueConstraint('submission_id', 'dataset_id', 'filename'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Submission (id and object) owning the executable.
    submission_id = Column(
        Integer,
        ForeignKey(Submission.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    submission = relationship(
        Submission)

    # Dataset (id and object) owning the executable.
    dataset_id = Column(
        Integer,
        ForeignKey(Dataset.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    dataset = relationship(
        Dataset)

    # SubmissionResult owning the executable.
    submission_result = relationship(
        SubmissionResult,
        backref=backref('executables',
                        collection_class=smart_mapped_collection('filename'),
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Filename and digest of the generated executable.
    filename = Column(
        String,
        nullable=False)
    digest = Column(
        String,
        nullable=False)


class Evaluation(Base):
    """Class to store information about the outcome of the evaluation
    of a submission against one testcase. Not to be used directly
    (import it from SQLAlchemyAll).

    """
    __tablename__ = 'evaluations'
    __table_args__ = (
        ForeignKeyConstraint(
            ('submission_id', 'dataset_id'),
            (SubmissionResult.submission_id, SubmissionResult.dataset_id),
            onupdate="CASCADE", ondelete="CASCADE"),
        UniqueConstraint('submission_id', 'dataset_id', 'testcase_id'),
    )

    # Auto increment primary key.
    id = Column(
        Integer,
        primary_key=True)

    # Submission (id and object) owning the evaluation.
    submission_id = Column(
        Integer,
        ForeignKey(Submission.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    submission = relationship(
        Submission)

    # Dataset (id and object) owning the evaluation.
    dataset_id = Column(
        Integer,
        ForeignKey(Dataset.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    dataset = relationship(
        Dataset)

    # SubmissionResult owning the evaluation.
    submission_result = relationship(
        SubmissionResult,
        backref=backref('evaluations',
                        cascade="all, delete-orphan",
                        passive_deletes=True))

    # Testcase (id and object) this evaluation was performed on.
    testcase_id = Column(
        Integer,
        ForeignKey(Testcase.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    testcase = relationship(
        Testcase)

    # String containing the outcome of the evaluation (usually 1.0,
    # ...) not necessary the points awarded, that will be computed by
    # the score type.
    outcome = Column(
        String,
        nullable=True)

    # String containing output from the grader (usually "Correct",
    # "Time limit", ...).
    text = Column(
        String,
        nullable=True)

    # Memory used by the evaluation, in bytes.
    memory_used = Column(
        Integer,
        nullable=True)

    # Evaluation's time and wall-clock time, in seconds.
    execution_time = Column(
        Float,
        nullable=True)
    execution_wall_clock_time = Column(
        Float,
        nullable=True)

    # Worker shard and sandbox where the evaluation was performed.
    evaluation_shard = Column(
        Integer,
        nullable=True)
    evaluation_sandbox = Column(
        String,
        nullable=True)

    @property
    def codename(self):
        return self.testcase.codename
