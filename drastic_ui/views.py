""""Drastic UI views
"""
__copyright__ = "Copyright (C) 2016 University of Maryland"
__license__ = "GNU AFFERO GENERAL PUBLIC LICENSE, Version 3"


from django.utils.translation import ugettext as _
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import logout

def home(request):
    if request.user and request.user.is_authenticated():
        return redirect('archive:home')
    return render(request, 'index.html', {})

def login_view(request):
    return render(request, 'login.html', {})

def logout_view(request):
    logout(request)
    messages.info(request, _("You have been logged out of Drastic"))
    return redirect("/")