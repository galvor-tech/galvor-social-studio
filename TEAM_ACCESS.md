# Team access, reviews and notifications: setup

The review workflow, the Team list and the in-app notifications (🔔) work now. Three one-time steps let
Sunil, Raj and Shrutik use the studio from their own laptops and get emailed. Steps 1 and 2 need a Google
Workspace admin; step 3 needs whoever manages galvor.ai's DNS on Cloudflare.

## 0. Check the Team list (2 min)
Open **Team** in the sidebar. Add Raj's and KC's Galvor emails (left blank on purpose so nothing is
sent to a guessed address). Confirm the roles:
- **Suyash**: admin, brand sign-off
- **Sunil**: approver, owns the "Sunil" voice, brand sign-off
- **Raj**: approver, owns "Raj"
- **Shrutik**: editor, owns "Shrutik"
- **KC**: viewer

## 1. Email notifications (5 min)
Use a Google Workspace account to send from (best: a shared `studio@galvor.com`; or your own).
1. On that account: Google Account → Security → turn on 2-Step Verification → **App passwords** → create one named "Galvor Studio".
2. Studio → **Settings → Notifications**: sender account = that address, app password = the 16 characters, port 587.
3. Click **Send me a test**. The delivery log under the button shows `EMAIL ok` or the exact error.

Optional: a Google Chat space for the content team. In Chat: space → Apps & integrations → Webhooks → add →
paste the URL into **Google Chat / Slack webhook**.

## 2. Google sign-in (5 min, Workspace admin)
1. https://console.cloud.google.com → create the project "Galvor Studio" (or reuse the CRM's project).
2. **APIs & Services → OAuth consent screen** → User type **Internal** (only galvor.com accounts) → app name "Galvor Social Studio".
3. **Credentials → Create credentials → OAuth client ID** → *Web application*. Add authorised redirect URIs:
   - `https://studio.galvor.ai/auth/callback`
   - `http://localhost:5055/auth/callback`
4. Copy the client ID and secret into **Settings → Access**. Set the web address to `https://studio.galvor.ai`.
   Tick **Require Google sign-in** → Save. From then on everyone (including you) signs in with Google.

The studio refuses to turn sign-in on unless your own email is an admin on the Team list, so you can't lock
yourself out. If it ever happens, set `"auth_mode": "off"` in `data/settings.json` and restart.

## 3. Make it reachable for the team (decision pending)
The studio's address is set to **https://studio.galvor.ai** (Settings → Access), and every email link and the
Google sign-in already use it. It isn't live yet:
- galvor.ai's DNS is on **Google Cloud DNS**, and a wildcard record already points `studio.galvor.ai` at the same
  Google load balancer as `crm.galvor.ai`. Nothing serves "studio" there yet, so the address is free to use.
- The Cloudflare Tunnel script (`tools/setup_tunnel.ps1`) **won't work for this address**: Cloudflare can only route
  hostnames whose DNS it manages. Keep it only if the studio ever moves to a Cloudflare-managed domain.
- When you're ready, the cleanest option is to deploy the studio to Cloud Run in the CRM's Google Cloud project and
  map `studio.galvor.ai` there. That needs someone with access to that project to run `gcloud auth login` once.

Until then the studio runs on this laptop at http://localhost:5055, and teammates can't open the links in
notification emails yet (they point to studio.galvor.ai). Google sign-in can be switched on now for this laptop
(it uses the localhost callback), but it only matters once the studio is hosted.

## What happens when someone clicks "Send for review"
1. The post is saved and checked; blocking issues stop it.
2. Status → **In review**. The studio picks the reviewer:
   - **Sunil / Raj / Shrutik posts** → that person.
   - **Company page, Instagram, newsletter** → brand sign-off (Suyash + Sunil).
   - **Any post that names a client or looks like a spend/ROAS claim** → also brand sign-off.
3. Reviewers get a 🔔 notification, an email with a button to the post, and a Chat message (if set).
4. Only the assigned reviewer or an admin sees **Approve / Send back**. Approving notifies the sender and author.
   Sending back notifies them with the reviewer's note. Every step is logged in the post's history with the person's name.
5. When a scheduled post's time arrives, the author and admins are told to post it, or told if auto-publish failed.
