#!/usr/bin/python3

#
# Disclaimer: Dirty workaround, i'm not responsible for anything, although it works for us
#
# simple webhook script for https://gitlab.com/gitlab-org/gitlab-ce/issues/21608#note_22185264
# uses https://github.com/burnettk/delete-docker-registry-image
#
# listens on POST requests containing JSON data from Gitlab webhook (on merge)
# it uses bottlepy, so setup like:
#   pip install bottle
# you can run it like
#   nohup /opt/registry-cleanup/python/registry-cleaner.py >> /var/log/registry-cleanup.log 2>&1 &
# also you need to put delete-docker-registry-image into the same directory:
#   curl -O https://raw.githubusercontent.com/burnettk/delete-docker-registry-image/master/delete_docker_registry_image.py
#
# you should also run registry garbage collection, either afterwards (might break your productive env) or at night (cronjob, better)
# gitlab-ctl registry-garbage-collect

import os
import logging
import aiohttp
from japronto import Application

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(u'%(levelname)-8s [%(asctime)s]  %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
# basic sec urity, add this token to the project's webhook
# get one:
# < /dev/urandom tr -dc _A-Z-a-z-0-9 | head -c"${1:-32}";echo;
token = os.getenv('CLEAN_TOKEN')
registry = os.getenv('REGISTRY_URL')
jwt_url = os.getenv('JWT_URL', None)
basic_auth = aiohttp.BasicAuth(login=os.getenv('REGISTRY_LOGIN'), password=os.getenv('REGISTRY_PASSWORD'))

if 'DRY_RUN' in os.environ:
    dry_run = True
else:
    dry_run = False


async def api(url, params=None, headers=None, auth=None):
    logger.info(url)
    print(url)
    async with aiohttp.ClientSession(headers=headers, auth=auth) as session:
        async with session.get(url, params=params) as response:
            return await response.json()


async def batch_remove(request):
    if 'clean-token' in request.query and request.query['clean-token'] == token:
        project_namespace = request.match_dict['project_namespace']
        project_name = request.match_dict['project_name']
        tag = request.match_dict['tag']
        logger.info(f"Valid request, processing {', '.join(request.match_dict.values())}")
        await cleanup(project_namespace, project_name, tag)
        return request.Response(text='ok')

    return request.Response(text='request not valid')


async def single_remove(request):
    if 'clean-token' in request.query and 'path' in request.query and request.query['clean-token'] == token:
        logger.info(f"Valid request, processing {request.query['path']}")
        image, tag = request.query['path'].split(':')
        await remove(image, tag)
        return request.Response(text='ok')

    return request.Response(text='request not valid')


async def cleanup(project_namespace, project_name, tag):
    logger.info("Merge detected")
    this_repo_image = "%s/%s" % (project_namespace, project_name)
    # find all images
    images = [this_repo_image]
    try:
        for i in os.listdir(f"{REGISTRY_DATA_DIR}/repositories/{this_repo_image}"):
            if i not in ['_layers', '_manifests', '_uploads']:
                images.append(f"{this_repo_image}/{i}")
    except Exception as e:
        print(e)
    # remove all images with this tag
    for image in images:
        await remove(image, tag)


async def remove(image, tag):
    go_to = f"{registry}/v2/{image}/manifests/{tag}"
    headers = {'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}
    if jwt_url:
        jwt = await api(jwt_url, auth=basic_auth)
        headers.update({"Authorization": f"Bearer {jwt['token']}"})
        print(headers)
    data = await api(go_to, headers=headers)
    print(data)


app = Application()
router = app.router
router.add_route('/{project_namespace}/{project_name}/{tag}', batch_remove)
router.add_route('/extra_path', single_remove)
app.run(host='0.0.0.0', port=80, debug=True)
