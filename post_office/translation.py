# -*- coding: utf-8 -*-
""" 
    @created: 15 giu 2017 
"""
from __future__ import absolute_import, print_function, unicode_literals

import logging

from django.utils.translation import ugettext, ugettext_lazy as _

from post_office.models import EmailTemplate


logger = logging.getLogger(__name__)

try:
    from modeltranslation.translator import translator, TranslationOptions
    
    class EmailTemplateTranslationOptions(TranslationOptions):
        fields = ('subject', 'content',) 
        #required_languages = {#'en': ('title', 'slug'),'default': () }
    
    #translator.register(EmailTemplate, EmailTemplateTranslationOptions)
except ImportError:
    pass
    
