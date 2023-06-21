#!/usr/bin/env python3

import re
from os import getenv
from hashlib import sha256
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .tracker import Tracker
from .schema import validate

app = FastAPI()

# Allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.on_event("startup")
async def startup():
    app.tracker = Tracker()
    await app.tracker.initialize()
    
@app.websocket("/")
async def on_connect(socket: WebSocket, token: str|None=None):
    await socket.accept()

    # First message is the peer ID
    try:
        peer_proof = await socket.receive_text()
    except:
        return

    if not re.match(r"^[0-9a-f]{64}$", peer_proof):
        try:
            await socket.send_json({
                'error': 'validation',
                'detail': 'invalid peer proof'
            })
        except:
            return
        return

    # Hash to get actual peer
    # (prevents peer impersonation)
    socket.peer = sha256(peer_proof.encode()).hexdigest()

    # Send it as proof
    try:
        await socket.send_json({
            'peer_id': socket.peer
        })
    except:
        return

    # Register with the pub/sub manager
    async with app.tracker.register(socket):

        # And reply back and forth
        while True:
            try:
                msg = await socket.receive_json()
                await reply(socket, msg)
            except:
                break

async def reply(socket, msg):
    # Initialize the output
    output = {}
    if 'messageID' in msg:
        output['messageID'] = msg['messageID']

    # Make sure the message is formatted properly
    try:
        validate(msg)
    except Exception as e:
        output['reply'] = 'error'
        output['detail'] = str(e).split('\n')[0]
        return await socket.send_json(output)

    # Pass it to the proper function
    action_function = getattr(app.tracker, msg["action"])
    output["reply"] = await action_function(msg["info_hashes"], socket)
    await socket.send_json(output)

if __name__ == "__main__":
    args = {}
    if getenv('DEBUG') == 'true':
        args['reload'] = True
    uvicorn.run('app.main:app', host='0.0.0.0', **args)