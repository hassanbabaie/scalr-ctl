__author__ = 'shaitanich'

import sys
import json
import click
import inspect
from scalrtools import settings
from scalrtools import request
from scalrtools.view import build_table, build_tree


enabled = False


class SubCommand(object):
    name = None
    route = None
    method = None
    enabled = False

    object_reference = None # optional, e.g. '#/definitions/GlobalVariable'
    mutable_body_parts = None # optional, object definitions in YAML spec are not always correct

    prompt_for = None #optional, Some values like GCE imageId cannot be passed through command line
    module = sys.modules[__name__] #XXX: temporary, inheretance problem quickfix

    @property
    def _basepath_uri(self):
        return settings.spec["basePath"]

    @property
    def _request_template(self):
        return "%s%s" % (self._basepath_uri, self.route)

    def modify_options(self, options):
        """
        this is the place where command line options can be fixed
        after they are loaded from yaml spec
        """
        #print "In SubCommand modifier"
        for option in options:
            if self.prompt_for and option.name in self.prompt_for:
                option.prompt = option.name

            if option.name == "envId" and settings.envId:
                option.required = False

        return options


    def pre(self, *args, **kwargs):
        """
        before request is made
        """
        edit = kwargs.pop("edit", False)

        if self.method.upper() in ("PATCH", "POST"):
            #prompting for body and then validating it
            for param in self._post_params():
                name = param["name"]

                if edit:
                    text = ''
                    try:
                        #XXX: rewrite, think of globals() or such
                        for name, obj in inspect.getmembers(self.module):
                            if inspect.isclass(obj):
                                if obj.route == self.route and obj.method.upper() == "GET":
                                    rawtext = obj().run(*args, **kwargs)
                                    json_text = json.loads(rawtext)
                                    filtered = self._filter_json_object(json_text['data'])
                                    text = json.dumps(filtered)
                    except (Exception, BaseException), e:
                        pass
                    raw = click.edit(text)

                else:
                    raw = click.termui.prompt("%s %s" % (name, "JSON"))

                try:
                    user_object = json.loads(raw)
                except (Exception, BaseException), e:
                    if settings.debug_mode:
                        raise
                    raise click.ClickException(str(e))

                valid_object = self._filter_json_object(user_object)
                valid_object_str = json.dumps(valid_object)
                kwargs[name] = valid_object_str
        return args, kwargs


    def post(self, response):
        """
        after request is made
        """
        return response


    def run(self, *args, **kwargs):
        """
        callback for click subcommand
        """
        args, kwargs = self.pre(*args, **kwargs)
        uri = self._request_template
        payload = {}
        data = None

        if settings.envId and '{envId}' in uri and ('envId' not in kwargs or not kwargs['envId']):
            kwargs['envId'] = settings.envId  # XXX

        if kwargs:
            uri = self._request_template.format(**kwargs)

            for key, value in kwargs.items():
                t = "{%s}" % key
                # filtering in-body and empty params
                if value and t not in self._request_template:
                    if self.method.upper() in ("GET", "DELETE"):
                        payload[key] = value
                    elif self.method.upper() in ("POST", "PATCH"):
                        data = value  #XXX

        raw_response = request.request(self.method, uri, payload, data)
        response = self.post(raw_response)

        if settings.view == "raw":
            click.echo(raw_response)

        if raw_response:

            response_json = json.loads(response)

            if "errors" in response_json and response_json["errors"]:
                raise click.ClickException(response_json["errors"][0]['message'])

            data = response_json["data"]
            text = json.dumps(data)

            if settings.debug_mode:
                click.echo(response_json["meta"])

            if settings.view == "tree":
                click.echo(build_tree(text))

            elif settings.view == "table":
                fields = ["Farm_ID", "Name", "Descriprion"]
                rows = [
                    ("1001", "Test_Farm", "First farm"),
                    ("1002", "Test_Farm_2", "Second farm"),
                ]
                click.echo(build_table(fields, rows, "Page: 1 of 1", "Total: 1"))

        return response


    def _list_mutable_body_parts(self):
        """
        finds object in yaml spec and determines it's mutable fields
        to filter user JSON
        """
        mutable = []
        spec = settings.spec

        if not self.object_reference:
            for param in spec["paths"][self.route][self.method]["parameters"]:
                name = param["name"] # image
                reference_path = param["schema"]['$ref'] # #/definitions/Image
        else:
            #XXX: Temporary code, see GlobalVariableDetailEnvelope or "role-global-variables update"
            reference_path = self.object_reference

        parts = reference_path.split("/")
        object =  spec[parts[1]][parts[2]]

        object_properties = object["properties"]
        for property, descr in object_properties.items():
            if 'readOnly' not in descr or not descr['readOnly']:
                    mutable.append(property)
        return mutable

    def _filter_json_object(self, obj):
        """
        removes immutable parts from JSON object before sending it in POST or PATCH
        """
        #XXX: make it recursive
        result = {}
        mutable_parts = self.mutable_body_parts or self._list_mutable_body_parts()
        for name, value in obj.items():
            if name in mutable_parts:
                result[name] = obj[name]
        return result

    def _post_params(self):
        """
        Determines list of body params
        e.g. 'image' JSON object for 'change-attributes' command
        """
        params = []
        m = settings.spec["paths"][self.route][self.method]
        if "parameters" in m:
            for parameter in m['parameters']:
                params.append(parameter)
        return params