#!/usr/bin/python
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2012 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

"""UserTest-related database interface for SQLAlchemy. Not to be used
directly (import from SQLAlchemyAll).

"""

from sqlalchemy.schema import Column, ForeignKey, UniqueConstraint
from sqlalchemy.types import Integer, Float, String, DateTime
from sqlalchemy.orm import relationship, backref
from sqlalchemy.orm.collections import attribute_mapped_collection

from SQLAlchemyUtils import Base
import SQLAlchemyAll as model

from cmscommon.DateTime import make_timestamp


class UserTest(Base):
    """Class to store a test requested by a user. Not to be used
    directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'user_tests'

    # Auto increment primary key.
    id = Column(Integer, primary_key=True)

    # User (id and object) that requested the test.
    user_id = Column(Integer,
                     ForeignKey("users.id",
                                onupdate="CASCADE", ondelete="CASCADE"),
                     nullable=False,
                     index=True)
    user = relationship(
        "User",
        back_populates='user_tests')

    # Task (id and object) of the test.
    task_id = Column(Integer,
                     ForeignKey("tasks.id",
                                onupdate="CASCADE", ondelete="CASCADE"),
                     nullable=False,
                     index=True)
    task = relationship(
        "Task",
        back_populates='user_tests')

    # Time of the request.
    timestamp = Column(DateTime, nullable=False)

    # Language of test, or None if not applicable.
    language = Column(String, nullable=True)

    # Input (provided by the user) and output files' digests for this
    # test
    input = Column(String, nullable=False)
    output = Column(String, nullable=True)

    # Compilation outcome (can be None = yet to compile, "ok" =
    # compilation successful and we can evaluate, "fail" =
    # compilation unsuccessful, throw it away).
    compilation_outcome = Column(String, nullable=True)

    # String containing output from the sandbox, and the compiler
    # stdout and stderr.
    compilation_text = Column(String, nullable=True)

    # Number of attempts of compilation.
    compilation_tries = Column(Integer, nullable=False, default=0)

    # Worker shard and sandbox where the compilation was performed
    compilation_shard = Column(Integer, nullable=True)
    compilation_sandbox = Column(String, nullable=True)

    # Evaluation outcome (can be None = yet to evaluate, "ok" =
    # evaluation successful).
    evaluation_outcome = Column(String, nullable=True)
    evaluation_text = Column(String, nullable=True)

    # Number of attempts of evaluation.
    evaluation_tries = Column(Integer, nullable=False, default=0)

    # Worker shard and sandbox wgere the evaluation was performed
    evaluation_shard = Column(Integer, nullable=True)
    evaluation_sandbox = Column(String, nullable=True)

    # Other information about the execution
    memory_used = Column(Integer, nullable=True)
    execution_time = Column(Float, nullable=True)

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    files = relationship(
        "UserTestFile",
        back_populates='user_test',
        collection_class=attribute_mapped_collection('filename'),
        cascade="all, delete-orphan",
        passive_deletes=True)
    executables = relationship(
        "UserTestExecutable",
        back_populates='user_test',
        collection_class=attribute_mapped_collection('filename'),
        cascade="all, delete-orphan",
        passive_deletes=True)
    managers = relationship(
        "UserTestManager",
        back_populates='user_test',
        collection_class=attribute_mapped_collection('filename'),
        cascade="all, delete-orphan",
        passive_deletes=True)

    def export_to_dict(self):
        """Return object data as a dictionary.

        """
        res = {
            'task': self.task.name,
            'timestamp': make_timestamp(self.timestamp),
            'files': [_file.export_to_dict()
                      for _file in self.files.itervalues()],
            'managers': [manager.export_to_dict()
                         for manager in self.managers.itervalues()],
            'input': self.input,
            'output': self.output,
            'language': self.language,
            'compilation_outcome': self.compilation_outcome,
            'compilation_tries': self.compilation_tries,
            'compilation_text': self.compilation_text,
            'compilation_shard': self.compilation_shard,
            'compilation_sandbox': self.compilation_sandbox,
            'executables': [executable.export_to_dict()
                            for executable
                            in self.executables.itervalues()],
            'evaluation_outcome': self.evaluation_outcome,
            'evaluation_text': self.evaluation_text,
            'evaluation_tries': self.evaluation_tries,
            'evaluation_shard': self.evalution_shard,
            'evaluation_sandbox': self.evaluation_sandbox,
            'memory_used': self.memory_used,
            'execution_time': self.execution_time,
            }
        return res

    def compiled(self):
        """Return if the user test has been compiled.

        return (bool): True if compiled, False otherwise.

        """
        return self.compilation_outcome is not None

    def evaluated(self):
        """Return if the user test has been evaluated.

        return (bool): True if evaluated, False otherwise.

        """
        return self.evaluation_outcome is not None


class UserTestFile(Base):
    """Class to store information about one file submitted within a
    user_test. Not to be used directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'user_test_files'
    __table_args__ = (
        UniqueConstraint('user_test_id', 'filename',
                         name='cst_files_user_test_id_filename'),
        )

    # Auto increment primary key.
    id = Column(Integer, primary_key=True)

    # Filename and digest of the submitted file.
    filename = Column(String, nullable=False)
    digest = Column(String, nullable=False)

    # Submission (id and object) of the submission.
    user_test_id = Column(Integer,
                          ForeignKey("user_tests.id",
                                     onupdate="CASCADE", ondelete="CASCADE"),
                          nullable=False,
                          index=True)
    user_test = relationship(
        "UserTest",
        back_populates='files')

    def export_to_dict(self):
        """Return object data as a dictionary.

        """
        return {
            'filename': self.filename,
            'digest': self.digest
            }


class UserTestExecutable(Base):
    """Class to store information about one file generated by the
    compilation of a user test. Not to be used directly (import it
    from SQLAlchemyAll).

    """
    __tablename__ = 'user_test_executables'
    __table_args__ = (
        UniqueConstraint('user_test_id', 'filename',
                         name='cst_executables_user_test_id_filename'),
        )

    # Auto increment primary key.
    id = Column(Integer, primary_key=True)

    # Filename and digest of the file.
    filename = Column(String, nullable=False)
    digest = Column(String, nullable=False)

    # Submission (id and object) of the submission.
    user_test_id = Column(Integer,
                          ForeignKey("user_tests.id",
                                     onupdate="CASCADE", ondelete="CASCADE"),
                          nullable=False,
                          index=True)
    user_test = relationship(
        "UserTest",
        back_populates='executables')

    def export_to_dict(self):
        """Return object data as a dictionary.

        """
        return {
            'filename': self.filename,
            'digest': self.digest
            }


class UserTestManager(Base):
    """Class to store additional files needed to compile or evaluate a
    user test (e.g., graders). Not to be used directly (import it from
    SQLAlchemyAll).

    """
    __tablename__ = 'user_test_managers'
    __table_args__ = (
        UniqueConstraint('user_test_id', 'filename',
                         name='cst_managers_user_test_id_filename'),
        )

    # Auto increment primary key.
    id = Column(Integer, primary_key=True)

    # Filename and digest of the manager.
    filename = Column(String, nullable=False)
    digest = Column(String, nullable=False)

    # Task (id and object) owning the manager.
    user_test_id = Column(Integer,
                          ForeignKey("user_tests.id",
                                     onupdate="CASCADE", ondelete="CASCADE"),
                          nullable=False,
                          index=True)
    user_test = relationship(
        "UserTest",
        back_populates='managers')

    def export_to_dict(self):
        """Return object data as a dictionary.

        """
        return {'filename': self.filename,
                'digest':   self.digest}
