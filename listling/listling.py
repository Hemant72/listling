# Open Listling
# Copyright (C) 2018 Open Listling contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# Affero General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.
# If not, see <https://www.gnu.org/licenses/>.

"""Open Listling core."""

from time import time

import micro
from micro import (Activity, Application, Collection, Editable, Location, Object, Orderable,
                   Trashable, Settings, Event, WithContent)
from micro.jsonredis import JSONRedis
from micro.util import randstr, run_instant, str_or_none, ON

from micro.jsonredis import RedisSortedSet

_USE_CASES = {
    'simple': {'title': 'New list', 'features': []},
    'todo': {'title': 'New to-do list', 'features': ['check']},
    'shopping': {'title': 'New shopping list', 'features': []},
    'meeting-agenda': {'title': 'New meeting agenda', 'features': []},
    'playlist': {'title': 'New playlist', 'features': ['play']},
    'map': {'title': 'New map', 'features': ['location']}
}

_EXAMPLE_DATA = {
    'todo': (
        'Project tasks',
        'Things we need to do to complete our project.',
        [
            {'title': 'Do research', 'checked': True},
            {'title': 'Create draft'},
            {'title': 'Write report', 'text': 'Summary of the results'}
        ]
    ),
    'shopping': (
        'Kitchen shopping list',
        'When you go shopping next time, please bring the items from this list.',
        [
            {'title': 'Soy sauce'},
            {'title': 'Vegetables', 'text': 'Especially tomatoes'},
            {'title': 'Chocolate (vegan)'}
        ]
    ),
    'meeting-agenda': (
        'Working group agenda',
        'We meet on Monday and discuss important issues.',
        [
            {'title': 'Round of introductions'},
            {'title': 'Lunch poll', 'text': 'What will we have for lunch today?'},
            {'title': 'Next meeting', 'text': 'When and where will our next meeting be?'}
        ]
    ),
    'playlist': (
        'Party playlist',
        'Songs we want to hear at our get-together tonight.',
        [
            {
                'title': 'Rick Astley - Never Gonna Give You Up',
                'text': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                'resource': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
            },
            {
                'title': 'Rihanna - Diamonds',
                'text': 'https://www.youtube.com/watch?v=lWA2pjMjpBs',
                'resource': 'https://www.youtube.com/watch?v=lWA2pjMjpBs'
            },
            {
                'title': 'Did you know?',
                'text': "The lyrics for Rihanna's song Diamonds were written by singer-songwriter Sia in just 14 minutes."
            }
        ]
    ),
    'map': (
        'Delicious burger places in Berlin',
        'Hand-Picked by ourselves. Your favorite is missing? Let us know!',
        [
            {
                'title': 'Glück to go',
                'text': 'Website: http://www.glueck-to-go.de/',
                'location': Location('Friesenstraße 26, 10965 Berlin, Germany',
                                     (52.48866, 13.394651))
            },
            {
                'title': 'L’herbivore',
                'text': 'Website: https://lherbivore.de/',
                'location': Location('Petersburger Straße 38, 10249 Berlin, Germany',
                                     (52.522951, 13.449482))
            },
            {
                'title': 'YELLOW SUNSHINE',
                'text': 'Website: http://www.yellow-sunshine.de/',
                'location': Location('Wiener Straße 19, 10999 Berlin, Germany',
                                     (52.497561, 13.430773))
            }
        ]
    )
}

class Listling(Application):
    """See :ref:`Listling`."""

    class Lists(Collection):
        """See :ref:`Lists`."""

        def create(self, use_case=None, description=None, title=None, v=1):
            """See :http:post:`/api/lists`."""
            if v == 1:
                # create(title, description=None)
                title = title or use_case
                if title is None:
                    raise TypeError()
                lst = self.create('simple', v=2)
                lst.edit(title=title, description=description)
                return lst
            if v == 2:
                # create(use_case='simple')
                use_case = use_case or 'simple'
            else:
                raise NotImplementedError()

            if not self.app.user:
                raise PermissionError()
            if use_case not in _USE_CASES:
                raise micro.ValueError('use_case_unknown')

            data = _USE_CASES[use_case]
            id = 'List:{}'.format(randstr())
            lst = List(
                id=id, app=self.app, authors=[self.app.user.id], title=data['title'],
                description=None, features=data['features'], mode='collaborate',
                activity=Activity('{}.activity'.format(id), self.app, subscriber_ids=[]))
            self.app.r.oset(lst.id, lst)
            self.app.r.rpush(self.map_key, lst.id)
            self.app.user.lists.add(lst, user=self.app.user)
            self.app.activity.publish(
                Event.create('create-list', None, {'lst': lst}, app=self.app))
            return lst

        def create_example(self, use_case, *, asynchronous=None):
            """See :http:post:`/api/lists/create-example`.

            .. deprecated:: 0.7.0

               Synchronous execution. Await instead (with *asynchronous* :data:`micro.util.ON`).
            """
            # Compatibility for synchronous execution (deprecated since 0.7.0)
            coro = self._create_example(use_case)
            return coro if asynchronous is ON else run_instant(coro)

        async def _create_example(self, use_case):
            if use_case not in _EXAMPLE_DATA:
                raise micro.ValueError('use_case_unknown')
            data = _EXAMPLE_DATA[use_case]
            description = (
                '{}\n\n*This example was created just for you, so please feel free to play around.*'
                .format(data[1]))

            lst = self.create(use_case, v=2)
            lst.edit(title=data[0], description=description)
            for item in data[2]:
                args = dict(item)
                checked = args.pop('checked', False)
                item = await lst.items.create(asynchronous=ON, **args)
                if checked:
                    item.check()
            return lst

    def __init__(self, redis_url='', email='bot@localhost', smtp_url='',
                 render_email_auth_message=None, *, video_service_keys={}):
        super().__init__(redis_url, email, smtp_url, render_email_auth_message,
                         video_service_keys=video_service_keys)
        self.types.update({'User': User, 'List': List, 'Item': Item})
        self.lists = Listling.Lists((self, 'lists'))

    def do_update(self):
        version = self.r.get('version')
        if not version:
            self.r.set('version', 7)
            return

        version = int(version)
        r = JSONRedis(self.r.r)
        r.caching = False

        # Deprecated since 0.3.0
        if version < 2:
            lists = r.omget(r.lrange('lists', 0, -1))
            for lst in lists:
                lst['features'] = []
                items = r.omget(r.lrange('{}.items'.format(lst['id']), 0, -1))
                for item in items:
                    item['checked'] = False
                r.omset({item['id']: item for item in items})
            r.omset({lst['id']: lst for lst in lists})
            r.set('version', 2)

        # Deprecated since 0.5.0
        if version < 3:
            lists = r.omget(r.lrange('lists', 0, -1))
            for lst in lists:
                lst['activity'] = (
                    Activity('{}.activity'.format(lst['id']), app=self, subscriber_ids=[]).json())
            r.omset({lst['id']: lst for lst in lists})
            r.set('version', 3)

        # Deprecated since 0.6.0
        if version < 4:
            items = r.omget([id for list_id in r.lrange('lists', 0, -1)
                             for id in r.lrange('{}.items'.format(list_id.decode()), 0, -1)])
            for item in items:
                item['location'] = None
            r.omset({item['id']: item for item in items})
            r.set('version', 4)

        # Deprecated since 0.7.0
        if version < 5:
            items = r.omget(
                [id for list_id in r.lrange('lists', 0, -1)
                 for id in r.lrange('{}.items'.format(list_id.decode()), 0, -1)])
            for item in items:
                item['resource'] = None
            r.omset({item['id']: item for item in items})
            r.set('version', 5)

        # Deprecated since 0.11.0
        if version < 6:
            lists = r.omget(r.lrange('lists', 0, -1))
            for lst in lists:
                lst['mode'] = 'collaborate'
            r.omset({lst['id']: lst for lst in lists})
            r.set('version', 6)

        # Deprecated since 0.14.0
        if version < 7:
            now = time()
            lists = r.omget(r.lrange('lists', 0, -1))
            for lst in lists:
                r.zadd('{}.lists'.format(lst['authors'][0]), {lst['id']: -now})
            r.set('version', 7)

    def create_user(self, data):
        return User(**data)

    def create_settings(self):
        # pylint: disable=unexpected-keyword-arg; decorated
        return Settings(
            id='Settings', app=self, authors=[], title='My Open Listling', icon=None,
            icon_small=None, icon_large=None, provider_name=None, provider_url=None,
            provider_description={}, feedback_url=None, staff=[], push_vapid_private_key=None,
            push_vapid_public_key=None, v=2)

class User(micro.User):
    """See :ref:`User`."""

    class Lists(Collection):
        """See :ref:`UserLists`."""
        # We use setattr / getattr to work around a Pylint error for Generic classes (see
        # https://github.com/PyCQA/pylint/issues/2443)

        def __init__(self, user):
            super().__init__(RedisSortedSet('{}.lists'.format(user.id), user.app.r), app=user.app)
            setattr(self, 'user', user)

        def add(self, lst, *, user):
            """See: :http:post:`/users/(id)/lists`."""
            if user != getattr(self, 'user'):
                raise PermissionError()
            self.app.r.zadd(self.ids.key, {lst.id: -time()})

        def remove(self, lst, *, user):
            """See :http:delete:`/users/(id)/lists/(list-id)`.

            If *lst* is not in the collection, a :exc:`micro.error.ValueError` is raised.
            """
            if user != getattr(self, 'user'):
                raise PermissionError()
            if lst.authors[0] == getattr(self, 'user'):
                raise micro.ValueError(
                    'user {} is owner of lst {}'.format(getattr(self, 'user').id, lst.id))
            if self.app.r.zrem(self.ids.key, lst.id) == 0:
                raise micro.ValueError(
                    'No lst {} in lists of user {}'.format(lst.id, getattr(self, 'user').id))

        def read(self, *, user):
            """Return collection for reading."""
            if user != getattr(self, 'user'):
                raise PermissionError()
            return self

    def __init__(self, **data):
        super().__init__(**data)
        self.lists = User.Lists(self)

    def json(self, restricted=False, include=False):
        return {
            **super().json(restricted=restricted, include=include),
            **({'lists': self.lists.json(restricted=restricted, include=include)}
               if restricted and self.app.user == self else {})
        }

class List(Object, Editable):
    """See :ref:`List`."""

    _PERMISSIONS = {
        'collaborate': {'user': {'list-modify', 'item-modify'}},
        'view':        {'user': set()}
    }

    class Items(Collection, Orderable):
        """See :ref:`Items`."""

        def create(self, title, text=None, *, resource=None, location=None, asynchronous=None):
            """See :http:post:`/api/lists/(id)/items`.

            .. deprecated:: 0.6.0

               *text* as positional argument. Pass as keyword argument instead.

            .. deprecated:: 0.7.0

               Synchronous execution. Await instead (with *asynchronous* :data:`micro.util.ON`).
            """
            coro = self._create(title, text=text, resource=resource, location=location)
            return coro if asynchronous is ON else run_instant(coro)

        async def _create(self, title, *, text=None, resource=None, location=None):
            # pylint: disable=protected-access; List is a friend
            self.host[0]._check_permission(self.app.user, 'list-modify')
            attrs = await WithContent.process_attrs({'text': text, 'resource': resource},
                                                    app=self.app)
            if str_or_none(title) is None:
                raise micro.ValueError('title_empty')

            item = Item(
                id='Item:{}'.format(randstr()), app=self.app, authors=[self.app.user.id],
                trashed=False, text=attrs['text'], resource=attrs['resource'],
                list_id=self.host[0].id, title=title,
                location=location.json() if location else None, checked=False)
            self.app.r.oset(item.id, item)
            self.app.r.rpush(self.map_key, item.id)
            self.host[0].activity.publish(
                Event.create('list-create-item', self.host[0], {'item': item}, self.app))
            return item

        def move(self, item, to):
            # pylint: disable=protected-access; List is a friend
            self.host[0]._check_permission(self.app.user, 'list-modify')
            super().move(item, to)

    def __init__(self, *, id, app, authors, title, description, features, mode, activity):
        super().__init__(id=id, app=app)
        Editable.__init__(self, authors=authors, activity=activity)
        self.title = title
        self.description = description
        self.features = features
        self.mode = mode
        self.items = List.Items((self, 'items'))
        self.activity = activity
        self.activity.host = self

    def do_edit(self, **attrs):
        self._check_permission(self.app.user, 'list-modify')
        if 'title' in attrs and str_or_none(attrs['title']) is None:
            raise micro.ValueError('title_empty')
        if 'features' in attrs and not set(attrs['features']) <= {'check', 'location', 'play'}:
            raise micro.ValueError('feature_unknown')
        if 'mode' in attrs and attrs['mode'] not in {'collaborate', 'view'}:
            raise micro.ValueError('Unknown mode')

        if 'title' in attrs:
            self.title = attrs['title']
        if 'description' in attrs:
            self.description = str_or_none(attrs['description'])
        if 'features' in attrs:
            self.features = attrs['features']
        if 'mode' in attrs:
            self.mode = attrs['mode']

    def json(self, restricted=False, include=False):
        return {
            **super().json(restricted, include),
            **Editable.json(self, restricted, include),
            'title': self.title,
            'description': self.description,
            'features': self.features,
            'mode': self.mode,
            'activity': self.activity.json(restricted),
            **({'items': self.items.json(restricted=restricted, include=include)} if restricted
               else {}),
        }

    def _check_permission(self, user, op):
        permissions = List._PERMISSIONS[self.mode]
        if not (user and (
                op in permissions['user'] or
                user == self.authors[0] or
                user in self.app.settings.staff)):
            raise PermissionError()

class Item(Object, Editable, Trashable, WithContent):
    """See :ref:`Item`."""

    def __init__(self, *, id, app, authors, trashed, text, resource, list_id, title, location=None,
                 checked):
        # Compatibility for Item without location (deprecated since 0.6.0)
        super().__init__(id, app)
        Editable.__init__(self, authors, lambda: self.list.activity)
        Trashable.__init__(self, trashed, lambda: self.list.activity)
        WithContent.__init__(self, text=text, resource=resource)
        self._list_id = list_id
        self.title = title
        self.location = Location.parse(location) if location else None
        self.checked = checked

    @property
    def list(self):
        # pylint: disable=missing-docstring; already documented
        return self.app.lists[self._list_id]

    def delete(self):
        self.app.r.lrem(self.list.items.ids.key, 1, self.id.encode())
        self.app.r.delete(self.id)

    def check(self):
        """See :http:post:`/api/lists/(list-id)/items/(id)/check`."""
        _check_feature(self.app.user, 'check', self)
        self._check_permission(self.app.user, 'item-modify')
        self.checked = True
        self.app.r.oset(self.id, self)
        self.list.activity.publish(Event.create('item-check', self, app=self.app))

    def uncheck(self):
        """See :http:post:`/api/lists/(list-id)/items/(id)/uncheck`."""
        _check_feature(self.app.user, 'check', self)
        self._check_permission(self.app.user, 'item-modify')
        self.checked = False
        self.app.r.oset(self.id, self)
        self.list.activity.publish(Event.create('item-uncheck', self, app=self.app))

    async def do_edit(self, **attrs):
        self._check_permission(self.app.user, 'item-modify')
        attrs = await WithContent.pre_edit(self, attrs)
        if 'title' in attrs and str_or_none(attrs['title']) is None:
            raise micro.ValueError('title_empty')

        WithContent.do_edit(self, **attrs)
        if 'title' in attrs:
            self.title = attrs['title']
        if 'location' in attrs:
            self.location = attrs['location']

    def trash(self):
        self._check_permission(self.app.user, 'item-modify')
        super().trash()

    def restore(self):
        self._check_permission(self.app.user, 'item-modify')
        super().restore()

    def json(self, restricted=False, include=False):
        return {
            **super().json(restricted, include),
            **Editable.json(self, restricted, include),
            **Trashable.json(self, restricted, include),
            **WithContent.json(self, restricted, include),
            'list_id': self._list_id,
            'title': self.title,
            'location': self.location.json() if self.location else None,
            'checked': self.checked
        }

    def _check_permission(self, user, op):
        lst = self.list
        # pylint: disable=protected-access; List is a friend
        permissions = List._PERMISSIONS[lst.mode]
        if not (user and (
                op in permissions['user'] or
                user == lst.authors[0] or
                user in self.app.settings.staff)):
            raise PermissionError()

def _check_feature(user, feature, item):
    if feature not in item.list.features:
        raise micro.ValueError('feature_disabled')
    if not user:
        raise PermissionError()
