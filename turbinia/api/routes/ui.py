# -*- coding: utf-8 -*-
# Copyright 2022 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Turbinia Web UI routes."""

import pathlib
import os

from fastapi import APIRouter, Depends
from fastapi import HTTPException
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, FileResponse
from turbinia.api.routes.auth import validate_auth

ui_router = APIRouter(tags=['Turbinia Web UI'])


@ui_router.get('/')
async def root(is_authenticated: bool = Depends(validate_auth)):
  """Default route."""
  if is_authenticated:
    return RedirectResponse('/web')
  return RedirectResponse('/login')


@ui_router.get('/web')
async def web(is_authenticated: bool = Depends(validate_auth)):
  """Serves the Web UI main page."""
  if is_authenticated:
    this_path = pathlib.Path(__file__).parent.resolve()
    static_content_path = this_path.parent.parent.parent.joinpath(
        'web/dist/index.html')
    if os.path.exists(static_content_path):
      response = FileResponse(
          path=static_content_path, headers={'Cache-Control': 'no-cache'})
      return response

  raise HTTPException(status_code=401, detail='Unauthorized')


@ui_router.get('/css/{catchall:path}')
async def serve_css(
    request: Request, is_authenticated: bool = Depends(validate_auth)):
  """Serves css content."""
  if is_authenticated:
    this_path = pathlib.Path(__file__).parent.resolve()
    static_content_path = this_path.parent.parent.parent.joinpath(
        'web/dist/css')
    path = request.path_params["catchall"]
    file = static_content_path.joinpath(path)
    if os.path.exists(file):
      return FileResponse(file)

  raise HTTPException(status_code=401, detail='Unauthorized')


@ui_router.get('/js/{catchall:path}')
async def serve_js(
    request: Request, is_authenticated: bool = Depends(validate_auth)):
  """Serves JavaScript content."""
  if is_authenticated:
    this_path = pathlib.Path(__file__).parent.resolve()
    static_content_path = this_path.parent.parent.parent.joinpath('web/dist/js')
    path = request.path_params["catchall"]
    file = static_content_path.joinpath(path)
    if os.path.exists(file):
      return FileResponse(file)

  raise HTTPException(status_code=401, detail='Unauthorized')
