import json
import os
import requests

from django.conf import settings
from django.http import (StreamingHttpResponse, HttpResponse,
                         Http404, HttpResponseForbidden)
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages


from archive.client import get_default_client
from archive.forms import CollectionForm
from users.authentication import administrator_required

from indigo.models.collection import Collection
from indigo.models.group import Group
from indigo.models.search import SearchIndex
from indigo.models.errors import UniqueException


@login_required()
def home(request):
    return redirect('archive:view', path='')

##############################################################################
# Collection specific view functions
##############################################################################

@login_required()
def resource_view(request, path):
    ctx = {"resource": {"id": id, "name": "A test name", "collection":{"name": "data"}}}

    client     = get_default_client()
    resource   = client.get_resource_info("/" + path)

    #if not resource.user_can(request.user, "read"):
    #    return HttpResponseForbidden()

    # Strip the leading / from the parent url
    if resource['parentURI'].startswith("/"):
        resource['parentURI'] = resource['parentURI'][1:]
    if resource['parentURI'] and not resource['parentURI'].endswith("/"):
        resource['parentURI'] = resource['parentURI'] + "/"
    resource['name'] = path.split('/')[-1]
    resource['path'] = path
    return render(request, 'archive/resource/view.html', {"resource": resource})

@login_required
def new_resource(request, container):
    # Requires write on container
    # Inherits perms from container by default.
    pass

@login_required
def edit_resource(request, id):
    # Requires edit on resource
    pass

@login_required
def delete_resource(request, id):
    # Requires delete on resource
    pass

##############################################################################
# Collection specific view functions
##############################################################################

@login_required()
def navigate(request, path):

    client     = get_default_client()
    collection = Collection.find_by_path(path or '/')

    if not collection:
        raise Http404()

    if not collection.user_can(request.user, "read"):
        return HttpResponseForbidden()

    paths = []
    full = ""
    for p in collection.path.split('/'):
        if not p:
            continue
        full = u"{}/{}".format(full, p)
        paths.append( (p,full,) )

    def child_collections():
        res = []
        for coll in collection.get_child_collections():
            if not collection.user_can(request.user, "read"):
                continue
            res.append(coll)
        return res

    ctx = {
        'collection': collection.to_dict(request.user),
        'child_collections': [c.to_dict(request.user) for c in child_collections()],
        'collection_paths': paths
    }

    return render(request, 'archive/index.html', ctx)


def search(request):
    query = request.GET.get('q')

    ctx = {
        "q": query
    }

    terms = [x.lower() for x in query.split(' ')]

    ctx['results'] = SearchIndex.find(terms, request.user)
    ctx['total'] = len(ctx['results'])
    ctx['highlights'] = terms

    return render(request, 'archive/search.html', ctx)

@login_required
def new_collection(request, parent):
    if not parent:
        parent_collection = Collection.get_root_collection()
    else:
        parent_collection = Collection.find_by_id(parent)

    if not parent_collection.user_can(request.user, "write"):
        return HttpResponseForbidden()

    form = CollectionForm(request.POST or None, initial={'metadata':'{"":""}'})
    if request.method == 'POST':
        if form.is_valid():
            data = form.cleaned_data
            try:
                name = data['name']
                parent = parent_collection.id
                metadata = {}
                for k, v in json.loads(data['metadata']):
                    metadata[k] = v
                collection = Collection.create(name=name,
                                               parent=parent,
                                               metadata=metadata,
                                               read_access=data['read_access'],
                                               write_access=data['write_access'],
                                               delete_access=data['delete_access'],
                                               edit_access=data['edit_access'])
                SearchIndex.index(collection, ['name', 'metadata'])
                messages.add_message(request, messages.INFO,
                                     u"New collection '{}' created" .format(collection.name))
                return redirect('archive:view', path=collection.path)
            except UniqueException:
                messages.add_message(request, messages.ERROR,
                                     "That name is in use in the current collection")

    groups = Group.objects.all()
    return render(request, 'archive/new.html', {'form': form, "parent": parent_collection, "groups": groups})

@login_required
def edit_collection(request, id):
    coll = Collection.find_by_id(id)

    if not coll.user_can(request.user, "edit"):
        return HttpResponseForbidden()

    if request.method == "POST":
        form = CollectionForm(request.POST)
        if form.is_valid():
            # TODO: Check for duplicates
            metadata = {}
            for k, v in json.loads(form.cleaned_data['metadata']):
                metadata[k] = v

            try:
                data = form.cleaned_data
                print data
                coll.update(name=data['name'],
                            metadata=metadata,
                            read_access=data['read_access'],
                            write_access=data['write_access'],
                            delete_access=data['delete_access'],
                            edit_access=data['edit_access'])

                SearchIndex.reset(coll.id)
                SearchIndex.index(coll, ['name', 'metadata'])

                return redirect('archive:view', path=coll.path)
            except UniqueException:
                messages.add_message(request, messages.ERROR,
                                     "That name is in use in the current collection")
    else:
        metadata = json.dumps(coll.metadata)
        if not coll.metadata:
            metadata = '{"":""}'

        initial_data = {'name':coll.name, 'metadata': metadata,
            'read_access': coll.read_access,
            'write_access': coll.write_access,
            'edit_access': coll.edit_access,
            'delete_access': coll.delete_access}
        form = CollectionForm(initial=initial_data)

    groups = Group.objects.all()
    return render(request, 'archive/edit.html', {'form': form, 'collection': coll, 'groups': groups})

@login_required
def delete_collection(request, id):
    coll = Collection.find_by_id(id)

    if not coll.user_can(request.user, "delete"):
        return HttpResponseForbidden()

    SearchIndex.reset(coll.id)

    return render(request, 'archive/delete.html', {})


@login_required
def download(request, path):
    """
    Requests for download are redirected to the agent via the agent,
    but for debugging the requests are served directly.

    We will send appropriate user auth to the agent.
    """

    # Permission checks

    client     = get_default_client()
    resource   = client.get_resource_info("/" + path)

    # We have size and mimetype from the resource info, then we want to
    # either:
    #   - Redirect to the appropriate agent URL
    #   - Stream the response ourselves, but only in debug

    def get_content_debug():
        yield client.get_resource_content("/" + path)

    if settings.DEBUG:
        resp = StreamingHttpResponse(streaming_content=get_content_debug(),
                                     content_type=resource.get('mimetype', 'application/octect-stream'))
        resp['Content-Disposition'] = 'attachment; filename="{}"'.format(path.split('/')[-1])

        return resp

    # TODO: Set the response in such a way that nginx can correctly redirect to the agent to do
    # the appropriate work of returning the file.

    return ""



