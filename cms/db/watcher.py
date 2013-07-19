#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2013 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

import gevent
from gevent import select

import psycopg2
from sqlalchemy.orm import class_mapper

from cms import logger
from cms.db import Base, custom_psycopg2_connection


class Watcher(object):
    EVENT_CREATE = "create"
    EVENT_UPDATE = "update"
    EVENT_DELETE = "delete"

    def __init__(self, init_callback):
        self._init_callback = init_callback
        self._callbacks = list()
        self._channels = set()

    def listen(self, callback, event, class_, *props):
        # Validate arguments
        if event not in ["create", "update", "delete"]:
            raise ValueError("Unknown event type.")

        if event != "update" and len(props) != 0:
            raise ValueError("Properties are only allowed for update events.")

        if not issubclass(class_, Base):
            raise ValueError("The class has to be an SQLAlchemy entity.")

        # Convert from SQLAlchemy ORM names to database layer.
        table_name = class_.__tablename__

        mapper = class_mapper(class_)
        cols = set()
        for prp in props:
            cols.update(col.name for col in mapper._props[prp].columns)

        # Store information.
        self._callbacks.append((callback, event, table_name, cols))
        self._channels.add((event, table_name))

    def run(self):
        while True:
            try:
                # Obtain a connection.
                conn = custom_psycopg2_connection()
                conn.autocommit = True

                # Execute all needed LISTEN queries.
                curs = conn.cursor()
                for event, table_name in self._channels:
                    curs.execute("LISTEN {0}_{1};".format(event, table_name))

                # Notify the service that we're ready to go: we're attached
                # to all notification channels. It can start fetching its
                # objects without fearing that we'll miss any update to them.
                gevent.spawn(self._init_callback)

                # Listen.
                while True:
                    select.select([conn],[],[])
                    conn.poll()

                    for notify in conn.notifies:
                        # Parse the notification.
                        event, _, table_name = notify.channel.partition('_')
                        rows = notify.payload.split('\n')
                        pkey = tuple(int(i) for i in rows[0].split(' '))
                        cols = set(rows[1:])

                        for item in self._callbacks:
                            if item[1] == event and item[2] == table_name and \
                                    (len(item[3]) == 0 or
                                     not item[3].isdisjoint(cols) > 0):
                                gevent.spawn(item[0], pkey, cols)

                    del conn.notifies[:]
            except psycopg2.OperationalError:
                logger.warning("Lost connection with database.")
                gevent.sleep(1)
