"""
WebSocket signaling relay for WebRTC.

Endpoint: WS /ws/meetings/{code}/{participant_id}

This is a pure relay — it does NOT process WebRTC media. It forwards
offer/answer/ice-candidate messages between participants, plus handles
host control messages (mute-all, kick).

Message format:
{
    "type": "offer" | "answer" | "ice-candidate" | "join" | "leave" | "mute-all" | "kick",
    "from": "<participant_id>",
    "to": "<participant_id> | null (broadcast)",
    "payload": { ... }
}
"""

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select, col
from ..models import Participant
from ..database import engine

router = APIRouter()

# Active WebSocket connections: { meeting_code: { participant_id: WebSocket } }
active_connections: dict[str, dict[str, WebSocket]] = {}


async def broadcast_to_room(code: str, message: dict, exclude_id: str = None):
    """Send a message to all participants in a room except the excluded one."""
    if code not in active_connections:
        return
    for pid, ws in active_connections[code].items():
        if pid != exclude_id:
            try:
                await ws.send_json(message)
            except Exception:
                pass  # Connection may have closed


async def send_to_participant(code: str, target_id: str, message: dict):
    """Send a message to a specific participant in a room."""
    if code in active_connections and target_id in active_connections[code]:
        try:
            await active_connections[code][target_id].send_json(message)
        except Exception:
            pass


def is_host(participant_id: str) -> bool:
    """Check if a participant has host privileges."""
    with Session(engine) as session:
        participant = session.get(Participant, int(participant_id))
        return participant.is_host if participant else False


@router.websocket("/ws/meetings/{code}/{participant_id}")
async def websocket_signaling(websocket: WebSocket, code: str, participant_id: str):
    """
    WebSocket endpoint for WebRTC signaling in a meeting room.
    
    Flow:
    1. Participant connects → added to active_connections
    2. 'join' broadcast sent to all existing participants
    3. Existing participants send offers to the new participant
    4. Messages are relayed: targeted (to specific peer) or broadcast
    5. On disconnect → 'leave' broadcast sent to remaining participants
    """
    await websocket.accept()

    # Initialize room if needed
    if code not in active_connections:
        active_connections[code] = {}

    # Store this connection
    active_connections[code][participant_id] = websocket

    # Get list of existing participants (before adding this one)
    existing_participants = [
        pid for pid in active_connections[code].keys()
        if pid != participant_id
    ]

    # Notify everyone that a new participant joined
    await broadcast_to_room(code, {
        "type": "join",
        "from": participant_id,
        "to": None,
        "payload": {
            "participant_id": participant_id,
            "existing_participants": existing_participants,
        }
    }, exclude_id=participant_id)

    # Send the new participant the list of who's already in the room
    await websocket.send_json({
        "type": "room-info",
        "from": "server",
        "to": participant_id,
        "payload": {
            "participants": existing_participants,
        }
    })

    try:
        while True:
            # Receive message from this participant
            raw = await websocket.receive_text()
            message = json.loads(raw)

            msg_type = message.get("type")
            target = message.get("to")

            # Always stamp the 'from' field server-side for security
            message["from"] = participant_id

            # ── Handle host-only control messages ──
            if msg_type == "mute-all":
                if is_host(participant_id):
                    await broadcast_to_room(code, message, exclude_id=participant_id)
                continue

            if msg_type == "kick":
                if is_host(participant_id) and target:
                    # Send kick message to target
                    await send_to_participant(code, target, message)
                    # Close their connection
                    if target in active_connections.get(code, {}):
                        target_ws = active_connections[code][target]
                        del active_connections[code][target]
                        await target_ws.close()
                        # Notify remaining participants
                        await broadcast_to_room(code, {
                            "type": "leave",
                            "from": target,
                            "to": None,
                            "payload": {"reason": "kicked"}
                        })
                continue

            # ── Chat messages — broadcast to all (ephemeral, not persisted) ──
            if msg_type == "chat":
                await broadcast_to_room(code, message, exclude_id=participant_id)
                continue

            # ── Reaction messages — broadcast to all ──
            if msg_type == "reaction":
                await broadcast_to_room(code, message, exclude_id=participant_id)
                continue

            # ── Waiting room messages ──
            if msg_type == "join-request":
                # Forward to host only — find the host in the room
                for pid, ws in active_connections.get(code, {}).items():
                    if pid != participant_id and is_host(pid):
                        try:
                            await ws.send_json(message)
                        except Exception:
                            pass
                continue

            if msg_type in ("admit", "deny"):
                # Host sends admit/deny to a specific waiting participant
                if is_host(participant_id) and target:
                    await send_to_participant(code, target, message)
                continue

            # ── Relay signaling messages (offer/answer/ice-candidate) ──
            if target:
                # Targeted message → send only to that participant
                await send_to_participant(code, target, message)
            else:
                # Broadcast → send to all others in the room
                await broadcast_to_room(code, message, exclude_id=participant_id)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error for participant {participant_id}: {e}")
    finally:
        # Clean up: remove from active connections
        if code in active_connections and participant_id in active_connections[code]:
            del active_connections[code][participant_id]

        # Clean up empty rooms
        if code in active_connections and len(active_connections[code]) == 0:
            del active_connections[code]

        # Notify remaining participants that this one left
        await broadcast_to_room(code, {
            "type": "leave",
            "from": participant_id,
            "to": None,
            "payload": {"reason": "disconnected"}
        })
