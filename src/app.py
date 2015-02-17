__author__ = 'shaitanich'

import os
import sys
import inspect

import yaml
import click

import commands
import settings


cmd_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), 'commands'))


class HelpBuilder(object):

    document = None

    def __init__(self, document):
        self.document = document

    def list_paths(self):
        return self.document["paths"].keys()

    def list_http_methods(self, path):
        l = self.document["paths"][path].keys()
        if "parameters" in l:
            l.remove("parameters")
        return l

    def get_method_description(self, path, method="get"):
        return self.document["paths"][path][method]['description']

    def get_body_type_params(self, path, method="get"):
        params = []
        m = self.document["paths"][path][method]
        if "parameters" in m:
            for parameter in m['parameters']:
                params.append(parameter)
        return params

    def get_path_type_params(self, path):
        params = []
        d = self.document["paths"][path]
        if "parameters" in d:
            for parameter in d['parameters']:
                params.append(parameter)
            return params

    def get_params(self, path, method="get"):
        return self.get_body_type_params(path, method) + self.get_path_type_params(path)


def list_module_filenames():
    files = os.listdir(cmd_folder)
    return [fname for fname in files if fname.endswith('.py') and not fname.startswith("_")]


class MyCLI(click.Group):

    _modules = None

    def __init__(self, name=None, commands=None, **attrs):
        click.Group.__init__(self, name, commands, **attrs)
        self._modules = {}
        self._init()

        current_dir = os.path.dirname(os.path.realpath(__file__))
        data = yaml.load(open(os.path.join(current_dir, "swagger.yaml"), "r"))
        self.hb = HelpBuilder(data)

    def _list_module_objects(self):
        return [module for module in self._modules.values() if module.enabled]

    def _list_subcommands(self, command_name):
        objects = []
        for name, obj in inspect.getmembers(self._modules[command_name]):
            if inspect.isclass(obj) and hasattr(obj, 'enabled') and getattr(obj, 'enabled'):
                subcommand = obj()
                if isinstance(subcommand, commands.SubCommand):
                    objects.append(subcommand)
        return objects

    def _list_options(self, subcommand):
        params = self.hb.get_params(subcommand.route, subcommand.method)
        options = []
        for param in params:
            option = click.Option(("--%s" % param['name'],), required=param['required'], help=param["description"])
            options.append(option)
        return options

    def _init(self):
        for name in list_module_filenames():
            try:
                if sys.version_info[0] == 2:
                    name = name.encode('ascii', 'replace')
                mod = __import__('commands.' + name[:-3], None, None, ['enabled'])
                if hasattr(mod, "name"):
                    self._modules[mod.name] = mod
            except ImportError:
                raise  # pass

    def list_commands(self, ctx):
        rv = [module.name for module in self._list_module_objects()]
        rv.sort()
        return rv

    def get_command(self, ctx, name):
        group = click.Group(name, callback=self._modules[name].callback)

        for subcommand in self._list_subcommands(name):
            if subcommand.route in self.hb.list_paths() \
                    and subcommand.method in self.hb.list_http_methods(subcommand.route):
                options = self._list_options(subcommand)
                help = self.hb.get_method_description(subcommand.route, subcommand.method)
                cmd = click.Command(subcommand.name, params=options, callback=subcommand.run, help=help)
                group.add_command(cmd)
        return group


@click.command(cls=MyCLI)
@click.version_option()
@click.pass_context
@click.option('--debug/--no-debug', default=False)
@click.option('--raw', is_flag=True, default=False)
def cli(ctx, debug, raw, *args, **kvargs):
    """Scalr-tools is a command-line interface to your Scalr account"""
    if debug:
        settings.debug_mode = debug
        click.echo("Debug mode: %s" % settings.debug_mode)
    if raw:
        settings.raw_view = raw

    #print('in outer')
    #print(args)
    #print(kvargs)

    pass


if __name__ == '__main__':
    cli()
