# homeassistant-bosch_dryer

This is a quick n' dirty component for Home Assistant to read the state of a Bosch Dryer using Home Connect. It likely works with other Home Connect dryers too.

This will give you four sensors for each Home Connect dryer you have:
- `door`: open, close, locked, or unknown. https://developer.home-connect.com/docs/status/door_state
- `program`: cotton, synthetic, ..., unknown. https://developer-staging.home-connect.com/docs/dryer/supported_programs_and_options
- `remaining`: time remaining in seconds, or unknown.
- `state`: inactive, ready, fun, finished, ..., or unavailable. https://developer.home-connect.com/docs/status/operation_state

## Automation ideas
My plan for this is to add a task to empty the dryer in Todoist when the dryer is finished. When the door opens, that task is automatically completed.

In addition, when the dryer is running, Magic Mirror displays the time remaining.

## Installation
- Ensure your dryer is set up and working in the Home Connect app.
- Copy this folder to `<config_dir>/custom_components/bosch_dryer/`.
- Create an account on https://developer.home-connect.com/.
- Register an application. Pick `Device flow` for OAuth flow.
- Once you star this sequence, you have 5 minutes to complete it (or you'll have to restart from here):
  - `export CLIENT_ID="YOUR_CLIENT_ID"`
  - `curl -X POST -H "Content-Type: application/x-www-form-urlencoded" -d "client_id=${CLIENT_ID}" https://api.home-connect.com/security/oauth/device_authorization | tee tmp.json`
  - Go to `verification_uri` in a browser, type in `user_code`. Log in using your (end user, not developer) Home Connect account and approve.
  - `export DEVICE_CODE=$(jq -r .device_code tmp.json)`
  - `curl -X POST -H "Content-Type: application/x-www-form-urlencoded" -d "grant_type=urn:ietf:params:oauth:grant-type:device_code&device_code=${DEVICE_CODE}&client_id=${CLIENT_ID}" https://api.home-connect.com/security/oauth/token | tee access_token.json`
  - `jq .refresh_token access_token.json`

Put the following in your home assistant config:
```
sensor:
  - platform: bosch_dryer
    client_id: "YOUR_CLIENT_ID"
    refresh_token: "YOUR_REFRESH_TOKEN"
```

## Remarks on the API
This is built using the Home Connect API, documented on https://developer.home-connect.com/. There is plenty in the API that is not exposed via this component. Using the API, one can also remote control the dryer, but I haven't figured out a use case for that yet. The API is a straightforward REST API with Oauth authentication. Best practice would likely be to only poll at startup and then use the streaming event API for updates. Instead, I just went with repeated state polling.

The API is a bit flakey, and tends to time out/return 504 during European evenings. I've written this component to retry all requests thrice to keep down the exception spam in the logs. Instead, you should expect to see warnings like:

```
2019-04-22 19:09:02 WARNING (MainThread) [homeassistant.helpers.entity] Update of sensor.bosch_wtwh75i9sn_state is taking over 10 seconds
2019-04-22 19:09:23 WARNING (MainThread) [homeassistant.components.sensor] Updating bosch_dryer sensor took longer than the scheduled update interval 0:00:30
```

If you're unlucky, flakeyness will hit when the component refreshes its access token on startup. If so, you'll need to restart. I'll probably make it more robust if I get sufficiently annoyed by it. That error will have the following in the middle of a large exception block:
```
    raise TokenExpiredError()
oauthlib.oauth2.rfc6749.errors.TokenExpiredError: (token_expired)

During handling of the above exception, another exception occurred:
...
oauthlib.oauth2.rfc6749.errors.CustomOAuth2Error: (SDK.Error.504.GatewayTimeout) Timeout on Home Connect subsystem. Please try it again.
```
