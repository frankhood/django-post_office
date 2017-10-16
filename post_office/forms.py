# -*- coding: utf-8 -*-
'''
Created on 16 ott 2017
'''

from django import forms
from django.conf import settings
from django.forms.utils import ErrorList
from django.utils.translation import ugettext_lazy as _

from .models import EmailTemplate
from .preview_utils import get_variables_from_content

class EmailTemplateAdminForm(forms.ModelForm):
 
    language = forms.ChoiceField(choices=settings.LANGUAGES, required=False, 
                                 help_text=_("Render template in alternative language"),
                                 label=_("Language"))
 
    class Meta:
        exclude = ()
        model = EmailTemplate
        fields = ('name', 'description', 'subject',
                  'content', 'html_content', 'language', 'default_template')

    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
                 initial=None, error_class=ErrorList, label_suffix=None,
                 empty_permitted=False, instance=None, use_required_attribute=None):
        super(EmailTemplateAdminForm, self).__init__(data, files, auto_id, prefix,
                 initial, error_class, label_suffix,
                 empty_permitted, instance, use_required_attribute)

        if self.instance:
            content = self.instance.content
            variables = get_variables_from_content(content)

            for var in variables:
                self.fields[var] = forms.CharField(label="{%s}"%(var), required=False)
