# -*- coding: utf-8 -*-
"""
git-recipe is a small recipe that allows you to use git
repositories

[buildout]
parts = data

[data]
recipe = gitrecipe
repository = git://example.com/my-git-repo.git
rev = origin/redevlop-branch
as_egg = true

"""

import os

from zc.buildout import easy_install
from zc.buildout import UserError

from subprocess import Popen
from subprocess import PIPE
from shutil import rmtree

from re import search
from re import findall
from re import MULTILINE

def get_reponame(url):
    if ":" in url:
        url = '/' + url.rsplit(":", 1)[1]
    match = search('\/(?P<repo_name>[a-zA-Z0-9-_.]*)(.git)$', url)
    if match:
        repo_name = match.groupdict()['repo_name']
        return repo_name
    else:
        raise UserError('Can not find repository name')


class GitRecipe(object):
    '''Simple recipe for fetch code form remote repository, using system git'''
    def __init__(self, buildout, name, options):
        self.options, self.buildout = options, buildout

        if 'repository' not in self.options:
            raise UserError('Repository url must be provided')
        self.url = options['repository']
        # ref option overrides rev
        if 'rev' in options:
            self.ref = options.get('rev', 'origin/master')
        if 'ref' in options:
            self.ref = options.get('ref', 'origin/master')

        self.as_egg = options.get('as_egg', 'false').lower() == 'true'
        self.options['download-directory'] = options.get('download-directory') or buildout['buildout']['parts-directory']

        # determine repository name
        repo_name = get_reponame(self.url)
        self.repo_path = os.path.join(self.options['download-directory'], repo_name)
        self.options['location'] = os.path.join(self.options['download-directory'], self.repo_path)

        self.paths = options.get('paths', None)
        if buildout['buildout'].get('offline').lower() == 'true':
            self.update = lambda: ()
        if self.options.get('newest', 'true').lower() == 'false':
            self.update = lambda: ()

    def git(self, operation, args, quiet=True):
        if quiet:
            command = ['git'] + [operation] + ['-q'] + args
        else:
            command = ['git'] + [operation] + args

        proc = Popen(' '.join(command), shell=True, stdout=PIPE)
        status = proc.wait()
        if status:
            raise UserError('Error while executing %s' % ' '.join(command))
        return proc.stdout.read()

    def check_same(self):
        old_cwd = os.getcwd()
        existing_repository = None

        if os.path.exists(self.repo_path) and os.path.exists(os.path.join(self.repo_path, '.git')):
            os.chdir(self.repo_path)
            origin = self.git('remote', ['show', 'origin'], quiet=False)
            existing_repository = findall('^\s*Fetch URL:\s*(.*)$', origin, flags=MULTILINE)[0]

        os.chdir(old_cwd)
        if existing_repository == self.url:
            return True

    def install(self):
        '''Clone repository and checkout to version'''
        # go to parts directory
        os.chdir(self.options['download-directory'])
        _installed = False

        try:

            if os.path.exists(self.repo_path):
                if self.check_same():
                    # If the same repository is here, just fetch new data and checkout to revision
                    # aka update ;)
                    _installed = True
                    os.chdir(self.repo_path)
                    self.git('fetch', [self.url, ])
                    if 'rev' in self.options:
                        os.chdir(self.options['location'])
                        self.git('checkout', [self.ref, ])
                        # return to root directory
                        os.chdir(self.buildout['buildout']['directory'])
                        #return self.options['location']

                else:
                    # if repository exists but not the same, delete all files there
                    rmtree(self.repo_path, ignore_errors=True)
                    _installed = False

            # in fact, the install
            if not _installed:
                os.chdir(self.options['download-directory'])
                self.git('clone', [self.url, ])
                # if revision is given, checkout to revision
                if 'rev' in self.options:
                    os.chdir(self.options['location'])
                    self.git('checkout', [self.ref, ])


        except UserError:
            # should manually clean files because buildout thinks that no files created
            rmtree(self.options['location'])
            raise


        if self.as_egg:
            self._install_as_egg()
        # return to root directory
        os.chdir(self.buildout['buildout']['directory'])
        return self.options['location']

    def update(self):
        '''Update repository rather than download it again'''
        # go to parts directory
        if self.check_same():
            os.chdir(self.options['location'])
            self.git('fetch', ['origin', ])
            # if revision is given, checkout to revision
            if 'rev' in self.options:
                self.git('checkout', [self.ref, ])
            if self.as_egg:
                self._install_as_egg()
        else:
            self.install()

        # return to root directory
        os.chdir(self.buildout['buildout']['directory'])
        return self.options['location']

    def _install_as_egg(self):
        """
        Install clone as development egg.
        """
        def _install(path, target):
            easy_install.develop(path, target)

        target = self.buildout['buildout']['develop-eggs-directory']
        if self.paths:
            for path in self.paths.split():
                path = os.path.join(self.options['location'], path.strip())
                _install(path, target)
        else:
            _install(self.options['location'], target)
