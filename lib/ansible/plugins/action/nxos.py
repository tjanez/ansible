#
# (c) 2016 Red Hat Inc.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import sys
import copy

from ansible.plugins.action.normal import ActionModule as _ActionModule
from ansible.utils.path import unfrackpath
from ansible.plugins import connection_loader
from ansible.compat.six import iteritems
from ansible.module_utils.nxos import nxos_argument_spec
from ansible.module_utils.basic import AnsibleFallbackNotFound
from ansible.module_utils._text import to_bytes

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()

class ActionModule(_ActionModule):

    def run(self, tmp=None, task_vars=None):
        if self._play_context.connection != 'local':
            return dict(
                failed=True,
                msg='invalid connection specified, expected connection=local, '
                    'got %s' % self._play_context.connection
            )

        provider = self.load_provider()
        transport = provider['transport'] or 'cli'

        if transport == 'cli':
            pc = copy.deepcopy(self._play_context)
            pc.connection = 'network_cli'
            pc.network_os = 'nxos'
            pc.port = provider['port'] or self._play_context.port or 22
            pc.remote_user = provider['username'] or self._play_context.connection_user
            pc.password = provider['password'] or self._play_context.password

            connection = self._shared_loader_obj.connection_loader.get('persistent', pc, sys.stdin)

            socket_path = self._get_socket_path(pc)
            if not os.path.exists(socket_path):
                # start the connection if it isn't started
                rc, out, err = connection.exec_command('open_shell()')
                display.vvv('open_shell() returned %s %s %s' % (rc, out, err))
                if rc != 0:
                    return {'failed': True, 'msg': 'unable to open shell', 'rc': rc}

            task_vars['ansible_socket'] = socket_path

        else:
            if provider['host'] is None:
                self._task.args['host'] = self._play_context.remote_addr
            if provider['username'] is None:
                self._task.args['username'] = self._play_context.connection_user
            if provider['password'] is None:
                self._task.args['password'] = self._play_context.password
            if provider['timeout'] is None:
                self._task.args['timeout'] = self._play_context.timeout
            if task_vars.get('nxapi_use_ssl'):
                self._task.args['use_ssl'] = task_vars['nxapi_use_ssl']
            if task_vars.get('nxapi_validate_certs'):
                self._task.args['validate_certs'] = task_vars['nxapi_validate_certs']


        result = super(ActionModule, self).run(tmp, task_vars)

        if transport == 'cli':
            display.vvv('closing cli shell', self._play_context.remote_addr)
            connection.exec_command('close_shell()')

        return result

    def _get_socket_path(self, play_context):
        ssh = connection_loader.get('ssh', class_only=True)
        cp = ssh._create_control_path(play_context.remote_addr, play_context.port, play_context.remote_user)
        path = unfrackpath("$HOME/.ansible/pc")
        return cp % dict(directory=path)

    def load_provider(self):
        provider = self._task.args.get('provider', {})
        for key, value in iteritems(nxos_argument_spec):
            if key != 'provider' and key not in provider:
                if key in self._task.args:
                    provider[key] = self._task.args[key]
                elif 'fallback' in value:
                    provider[key] = self._fallback(value['fallback'])
                elif key not in provider:
                    provider[key] = None
        return provider

    def _fallback(self, fallback):
        strategy = fallback[0]
        args = []
        kwargs = {}

        for item in fallback[1:]:
            if isinstance(item, dict):
                kwargs = item
            else:
                args = item
        try:
            return strategy(*args, **kwargs)
        except AnsibleFallbackNotFound:
            pass


