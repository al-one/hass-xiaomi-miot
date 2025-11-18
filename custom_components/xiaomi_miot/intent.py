import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.const import Platform, ATTR_ENTITY_ID
from homeassistant.helpers import intent

_LOGGER = logging.getLogger(__name__)


async def async_setup_intents(hass: HomeAssistant):
    """Set up the intents."""
    intent.async_register(hass, XiaoaiPlayText())
    intent.async_register(hass, XiaoaiExecuteCommand())


def match_states_from_slots(intent_obj, slots, domains=None):
    match_constraints = intent.MatchTargetsConstraints(
        name=slots.get('name', {}).get('value'),
        area_name=slots.get('area', {}).get('value'),
        floor_name=slots.get('floor', {}).get('value'),
        domains=domains,
        assistant=intent_obj.assistant,
        single_target=True,
    )
    match_preferences = intent.MatchTargetsPreferences(
        area_id=slots.get('preferred_area_id', {}).get('value'),
        floor_id=slots.get('preferred_floor_id', {}).get('value'),
    )
    match_result = intent.async_match_targets(
        intent_obj.hass, match_constraints, match_preferences
    )
    if not match_result.is_match:
        raise intent.MatchFailedError(
            result=match_result, constraints=match_constraints
        )
    assert match_result.states
    return match_result.states


class XiaoaiPlayText(intent.IntentHandler):
    intent_type = 'XiaoaiPlayText'
    description = 'Convert text to sound and play on the Xiaoai speaker or Xiaomi TV'
    slot_schema = {
        vol.Required('message', description='Message content'): intent.non_empty_string,
        vol.Optional('name', description='Name of the Xiaoai speaker or Xiaomi TV'): intent.non_empty_string,
        vol.Optional('area'): intent.non_empty_string,
        vol.Optional('floor'): intent.non_empty_string,
        vol.Optional('preferred_area_id'): str,
        vol.Optional('preferred_floor_id'): str,
    }
    platforms = {Platform.MEDIA_PLAYER}

    async def async_handle(self, intent_obj: intent.Intent):
        """Handle the intent."""
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        states = match_states_from_slots(intent_obj, slots, [Platform.MEDIA_PLAYER])
        state = states[0]
        for sta in states:
            if 'xiaomi' in state.entity_id:
                state = sta
                break

        message = slots.get('message', {}).get('value')
        await hass.services.async_call(
            'xiaomi_miot',
            'intelligent_speaker',
            target={ATTR_ENTITY_ID: state.entity_id},
            service_data={
                'text': message,
                'execute': False,
            },
            blocking=True,
        )

        response = intent_obj.create_response()
        response.response_type = intent.IntentResponseType.ACTION_DONE
        response.async_set_results(
            success_results=[
                intent.IntentResponseTarget(
                    name=str(state.name),
                    type=intent.IntentResponseTargetType.ENTITY,
                    id=state.entity_id,
                ),
            ],
        )
        return response


class XiaoaiExecuteCommand(intent.IntentHandler):
    intent_type = 'XiaoaiExecuteCommand'
    description = 'Execute commands on the Xiaoai speaker or Xiaomi TV'
    slot_schema = {
        vol.Required('command', description='Command content'): intent.non_empty_string,
        vol.Optional('name', description='Name of the Xiaoai speaker or Xiaomi TV'): intent.non_empty_string,
        vol.Optional('area'): intent.non_empty_string,
        vol.Optional('floor'): intent.non_empty_string,
        vol.Optional('preferred_area_id'): str,
        vol.Optional('preferred_floor_id'): str,
    }
    platforms = {Platform.MEDIA_PLAYER}

    async def async_handle(self, intent_obj: intent.Intent):
        """Handle the intent."""
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        states = match_states_from_slots(intent_obj, slots, [Platform.MEDIA_PLAYER])
        state = states[0]
        for sta in states:
            if 'xiaomi' in state.entity_id:
                state = sta
                break

        command = slots.get('command', {}).get('value')
        await hass.services.async_call(
            'xiaomi_miot',
            'intelligent_speaker',
            target={ATTR_ENTITY_ID: state.entity_id},
            service_data={
                'text': command,
                'execute': True,
            },
            blocking=True,
        )

        response = intent_obj.create_response()
        response.response_type = intent.IntentResponseType.ACTION_DONE
        response.async_set_results(
            success_results=[
                intent.IntentResponseTarget(
                    name=str(state.name),
                    type=intent.IntentResponseTargetType.ENTITY,
                    id=state.entity_id,
                ),
            ],
        )
        return response
