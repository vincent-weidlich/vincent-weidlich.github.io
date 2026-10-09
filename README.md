# Vincent Weidlich research website

A static research website with four selected publications, paper summaries, German and Russian overview pages, a citation download, and automated GitHub Pages deployment. Python 3.10 or newer is sufficient; no packages need installing.

Repository: `vincent-weidlich/vincent-weidlich.github.io`  
Website after deployment: `https://vincent-weidlich.github.io/`

## Publish on GitHub

1. Sign in to the **vincent-weidlich** GitHub account and create a **public** repository named **vincent-weidlich.github.io**. Add a README to initialize it. Use the default branch `main`.
2. Open **Settings → Pages**. Under **Build and deployment → Source**, select **GitHub Actions**. This workflow builds the HTML itself; do not select a Jekyll template.
3. Upload the **contents** of this source folder to the repository root, preserving the `data`, `assets`, `scripts`, and `.github/workflows` folders. Do not upload the ZIP as a single file or place everything inside an extra outer folder. On Ubuntu, **Ctrl+H** reveals the `.github` folder. Replace the initial README with this one. The generated `dist` folder does not need uploading.
4. If the upload interface omits hidden folders, use **Add file → Create new file**, name it `.github/workflows/deploy.yml`, and paste the exact contents of the supplied workflow file.
5. Commit to `main`. In **Actions**, open **Deploy research website**. A successful run builds, checks and publishes the site. It then attempts an IndexNow notification for changed pages. Check the notification step separately from the deployment result.
6. Open **Settings → Pages → Visit site**. Confirm the homepage, a paper page, `/sitemap.xml`, and `/robots.txt` load. If the first run started before Pages was enabled, run **Actions → Deploy research website → Run workflow** after completing step 2.

All website source is intended for a public repository. Upload only this folder; the private planning report and other workspace files are not part of the website.

[GitHub Pages setup](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site) · [Custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

## Verify Google Search Console

The website must be publicly live first. There is no website code to paste into Search Console.

1. Open [Google Search Console](https://search.google.com/search-console/) in the Google account that should manage the site.
2. Select **Add property → URL prefix**, and enter **https://vincent-weidlich.github.io/**. Use URL prefix because you do not control DNS for `github.io`.
3. Choose **HTML tag** under the available verification methods. Google displays a tag such as `<meta name="google-site-verification" content="YOUR_VALUE">`.
4. In your GitHub repository, edit `data/site.json`. Replace the empty value of `google_site_verification` with **only the value inside `content="..."`**. Preserve the JSON quotes and commas, then commit the change to `main`.
5. Wait for the deployment workflow to finish. Open the public homepage's source and confirm the `google-site-verification` tag is present. Return to Search Console and press **Verify**. Keep the verification value in place afterward.
6. Open **Sitemaps**, enter **sitemap.xml**, and submit. The complete address is **https://vincent-weidlich.github.io/sitemap.xml**.
7. Use **URL inspection** on the homepage and `/publications/`, then **Request indexing** if available. Review indexing results later; submitting does not guarantee inclusion or ranking.

Alternative: set a repository Actions **variable** called `GOOGLE_SITE_VERIFICATION` to the content value. Variables override the JSON value; after changing a variable, manually run the workflow because variable changes do not create commits.

For a future custom domain, configure the domain in GitHub Pages and at its DNS provider. The workflow reads the Pages address automatically. Then add the new address to Search Console; a Domain property requires DNS verification.

[Verification methods](https://support.google.com/webmasters/answer/9008080?hl=en) · [Property types](https://support.google.com/webmasters/answer/34592?hl=en) · [Sitemaps report](https://support.google.com/webmasters/answer/7451001?hl=en) · [Indexing requests](https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl)

## Automatic change notifications

The workflow records the live website's content hashes before deploying. After a successful deployment it compares them with the new build, checks the hosted ownership key and the actual live page contents, and submits only new, changed or removed URLs to IndexNow. The random ownership key is already configured; its matching public verification file is generated automatically.

An unchanged build sends no notification. A failed live-content check sends no notification. If the previous site cannot be read, the notification is skipped with a warning. A 404 on the initial manifest is treated as the first deployment.

HTTP 200 means receipt; HTTP 202 means ownership validation is pending. Neither confirms indexing. A notification failure does not undo a successful website deployment. Inspect the workflow's notification step for the outcome.

This targets participating search engines through [IndexNow](https://www.indexnow.org/documentation). Google uses the Search Console steps above. Research databases require their own profile, publisher or repository workflows; this code does not submit third-party pages as if they belonged to this website.

## Edit the website

- `data/site.json`: name, profile links, selected DOI list, Google verification value and IndexNow key.
- `data/publications.json`: the four selected papers, author order, dates, summaries and original-record links.
- `assets/style.css`: responsive appearance.
- `scripts/build_site.py`: generates only the selected content into `dist/`.
- `scripts/check_site.py`: validates links, canonical URLs, publication selection, sitemap, verification tag and indexing mode.
- `scripts/notify_indexnow.py`: change detection and optional IndexNow submission.
- `.github/workflows/deploy.yml`: builds and publishes on changes to `main`, or a manual workflow run.

Keep the label **Selected publications**. Additions require updating both the selected DOI list and the publication records. No full-bibliography import is enabled. Paper pages are labeled summaries and link to the actual publications. Do not add unconfirmed appointments, degrees or credentials to the profile.

## Run locally

From this source folder:

```bash
python3 scripts/build_site.py
python3 scripts/check_site.py
python3 -m http.server 8766 --bind 127.0.0.1 --directory dist
```

Open `http://127.0.0.1:8766/`. Local builds have `noindex` and block crawlers. GitHub builds run with `--production`, which produces public HTTPS canonical URLs and allows crawling.

To check the production build without publishing:

```bash
python3 scripts/build_site.py --production --base-url https://vincent-weidlich.github.io/
python3 scripts/check_site.py --production --base-url https://vincent-weidlich.github.io/
```

Re-run the ordinary local build afterward to restore preview links. Production checks alone make no network submissions. Deployment and IndexNow require a live, owned website.

## Source and permissions

Publication metadata and short summaries were checked against the linked PubMed records. Full papers and figures are linked at their original hosts rather than copied here. The German and Russian overview copy should be reviewed when making substantive changes.

GitHub Actions uses the official GitHub checkout and Pages actions. It receives a temporary repository workflow token; no personal access token is embedded in this source.
