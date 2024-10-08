import os
import re
from django.template import Library
from django.template.base import (
    TemplateSyntaxError, Node, Variable, token_kwargs)
from collections import defaultdict
from django.forms.utils import flatatt
from django.forms.boundfield import BoundField
from django.template.loader import get_template
from django.template.loader_tags import IncludeNode
from django.utils.safestring import mark_safe
from ..compat import context_flatten

register = Library()

ATTRS_RE = re.compile(r'(?P<attr>[-\w]+)(\s*=\s*[\'"](?P<val>.*?)[\'"])?', re.MULTILINE | re.DOTALL)


def _render_parts(context, parts_list):
    parts = context['form_parts']
    for partnode in parts_list:
        part = partnode.resolve_part(context)
        if partnode.section not in parts[part]:
            value = partnode.render(context)
            parts[part][partnode.section] = value


@register.tag('form')
class FormNode(Node):
    def __init__(self, parser, token):  
        bits = token.split_contents()
        remaining_bits = bits[1:]
        self.kwargs = token_kwargs(remaining_bits, parser)
        if remaining_bits:
            raise TemplateSyntaxError("%r received an invalid token: %r" % (bits[0], remaining_bits[0]))
        for key in self.kwargs:
            if key not in ('form', 'layout', 'template'):
                raise TemplateSyntaxError("%r received an invalid key: %r" % (bits[0], key))
            self.kwargs[key] = self.kwargs[key]
        self.nodelist = parser.parse(('end{}'.format(bits[0])))
        parser.delete_first_token()

    def render(self, context):  
        form = self.kwargs.get('form')
        form = form.resolve(context) if form else context.get('form')
        if form is None:
            return ''
        layout = self.kwargs.get('layout')
        if layout is not None:
            layout = layout.resolve(context)
        if layout is None:
            if 'view' in context:
                view = context['view']
                if hasattr(view, 'layout'):
                    layout = view.layout
        if layout is None:
            if hasattr(form, 'layout'):
                layout = form.layout
        template_name = self.kwargs.get('template', 'material/form.html')
        template = get_template(template_name)
        parts = defaultdict(dict)
        attrs = defaultdict(dict)
        with context.push(
                form=form,
                layout=layout,
                form_template_pack=os.path.dirname(template_name),
                form_parts=parts,
                form_widget_attrs=attrs):
            children = (node for node in self.nodelist if isinstance(node, FormPartNode))
            _render_parts(context, children)
            attrs = (node for node in self.nodelist if isinstance(node, WidgetAttrNode))
            for attr in attrs:
                attr.render(context)
            children = (node for node in self.nodelist if isinstance(node, IncludeNode))
            for included_list in children:
                included = included_list.template.resolve(context)
                children = (node for node in included.nodelist if isinstance(node, FormPartNode))
                _render_parts(context, children)
                attrs = (node for node in self.nodelist if isinstance(node, WidgetAttrNode))
                for attr in attrs:
                    attr.render(context)
            return template.render(context_flatten(context))


@register.tag('part')
class FormPartNode(Node):
    def __init__(self, parser, token):  
        bits = token.split_contents()
        if len(bits) > 5:
            raise TemplateSyntaxError("%r accepts at most 4 arguments (part_id, section, asvar, varname), got: {}".format(bits[0], ','.join(bits[1:])))
        self.part_id = Variable(bits[1])
        self.section = bits[2] if len(bits) >= 3 else None
        self.varname = None
        if len(bits) > 3:
            if bits[3] != 'asvar':
                raise TemplateSyntaxError('Fourth argument should be "asvar", got {}'.format(bits[3]))
            if len(bits) < 4:
                raise TemplateSyntaxError('Variable name not provided')
            else:
                self.varname = Variable(bits[4])
        self.nodelist = parser.parse(('end{}'.format(bits[0]),))
        parser.delete_first_token()

    def resolve_part(self, context):
        part = self.part_id.resolve(context)
        if isinstance(part, BoundField):
            part = part.field
        return part

    def render(self, context):  
        part = self.resolve_part(context)
        parts = context['form_parts']
        if self.section in parts[part]:
            if self.varname is not None:
                varname = self.varname.resolve(context)
                context[varname] = parts[part][self.section]
                return ""
            else:
                return parts[part][self.section]
        children = (node for node in self.nodelist if isinstance(node, FormPartNode))
        _render_parts(context, children)
        value = self.nodelist.render(context).strip()
        if self.varname is not None:
            context[self.varname.resolve(context)] = value
            return ''
        else:
            if not value:
                return ''
            return value


@register.tag('attrs')
class WidgetAttrsNode(Node):
    def __init__(self, parser, token):  
        bits = token.split_contents()
        if len(bits) < 3:
            raise TemplateSyntaxError("%r accepts at least 2 arguments (bound_field, 'groupname'), got: {}".format(bits[0], ','.join(bits[1:])))
        if len(bits) > 5:
            raise TemplateSyntaxError("%r accepts at most 4 arguments (bound_field, 'groupname' default attrs_dict), got: {}".format(bits[0], ','.join(bits[1:])))
        if len(bits) > 3 and bits[3] != 'default':
            raise TemplateSyntaxError("%r third argument should be 'default', got: {}".format(bits[0], ','.join(bits[1:])))
        self.field = Variable(bits[1])
        self.group = Variable(bits[2])
        self.widget_attrs = Variable(bits[4]) if len(bits) >= 5 else None
        self.nodelist = parser.parse(('end{}'.format(bits[0])))
        parser.delete_first_token()

    def resolve_field(self, context):
        field = self.field.resolve(context)
        if isinstance(field, BoundField):
            field = field.field
        return field

    def render(self, context):  
        field = self.resolve_field(context)
        group = self.group.resolve(context)
        form_widget_attrs = context['form_widget_attrs']
        override = {}
        if group in form_widget_attrs[field]:
            override = form_widget_attrs[field][group]
        build_in_attrs, tag_content = {}, self.nodelist.render(context)
        for attr, _, value in ATTRS_RE.findall(tag_content):
            build_in_attrs[attr] = mark_safe(value) if value != '' else True
        widget_attrs = {}
        if self.widget_attrs is not None:
            widget_attrs = self.widget_attrs.resolve(context)
        result = build_in_attrs.copy()
        if 'class' in result and 'class' in widget_attrs:
            result['class'] += ' ' + widget_attrs.pop('class')
        result.update(widget_attrs)
        for attr, (value, action) in override.items():
            if action == 'override':
                result[attr] = value
            elif action == 'append':
                if attr in result:
                    result[attr] += " " + value
                else:
                    result[attr] = value
        return flatatt(result)


@register.tag('attr')
class WidgetAttrNode(Node):
    def __init__(self, parser, token):  
        bits = token.split_contents()
        if len(bits) < 4:
            raise TemplateSyntaxError("{} accepts at least 3 arguments (bound_field, 'groupname' 'attr_name'), got: {}".format(bits[0], ','.join(bits[1:])))
        if len(bits) > 5:
            raise TemplateSyntaxError("{} accepts at most 4 arguments (bound_field, 'groupname' 'attr_name' action), got: {}".format(bits[0], ','.join(bits[1:])))
        if len(bits) >= 5 and bits[4] not in ['append', 'override']:
            raise TemplateSyntaxError("{} unknown action {}. Should be 'append' or 'override'".format(bits[0], bits[4]))
        self.field = Variable(bits[1])
        self.group = Variable(bits[2])
        self.attr = bits[3]
        self.action = bits[4] if len(bits) >= 5 else 'override'
        self.nodelist = parser.parse(('end{}'.format(bits[0])))
        parser.delete_first_token()

    def resolve_field(self, context):
        field = self.field.resolve(context)
        if isinstance(field, BoundField):
            field = field.field
        return field

    def render(self, context):  
        field = self.resolve_field(context)
        group = self.group.resolve(context)
        form_widget_attrs = context['form_widget_attrs']
        value = self.nodelist.render(context)
        if group not in form_widget_attrs[field]:
            form_widget_attrs[field][group] = {}
        attrs = form_widget_attrs[field][group]
        attrs[self.attr] = (value, self.action)
        return ''
