<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Application structure
- Content routes render a shared TransitHear shell and view module so navigation and accessibility controls remain consistent.
- This is a frontend interactive prototype: label simulated data and integrations explicitly; never imply live transcription, verified facilities, ISL translation, or actual wearable connectivity without integration.
- Use global semantic design tokens for all visual roles, including facility statuses and transit alert colors, to preserve a consistent palette.
