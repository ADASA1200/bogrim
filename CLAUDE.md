# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Hebrew (RTL) alumni management system ("מערכת ניהול בוגרים") for ישיבת באר התלמוד. The code is an export from a **Base44** app: React pages/components that talk to the Base44 backend through `base44.entities.<Entity>` (e.g. `base44.entities.Alumni.create(data)`), with `@tanstack/react-query` for data fetching/mutations, `react-router-dom` for routing, shadcn/ui components (`@/components/ui/*`), `lucide-react` icons, `sonner` toasts and Tailwind classes.

## Current state of the repository (important)

- There is **no build setup**: no `package.json`, no bundler/lint/test config, no `src/` tree. Nothing can be built, linted or tested from this repo as-is.
- All `.js` files sit flat in the repo root, but their imports assume the original Base44 layout (`@/api/base44Client`, `@/components/ui/...`, `../utils`, `../components/alumni/SuggestFamilyDialog`, `./utils`). Those imported modules are not in the repo.
- **The uploaded files are broken**: 15 of the 16 files are byte-identical copies of the same truncated `AddAlumniPage` component (cut off mid-`useMutation`). `Layout.js` is the only distinct file, and it is also truncated (ends mid-JSX). Do not assume any file's content matches its name; check with `md5sum *.js` before working on one. The real sources need to be re-exported from Base44 and re-uploaded.
- There are duplicate names from the upload (`Alumni.js`, `Alumni (2).js`, `alumni (1).js`).

## Domain model (from the visible code)

`Alumni` entity fields: `first_name`, `last_name`, `phone`, `email`, `current_city`, `current_street`, `parent_city`, `parent_street`, `parent_house_number`, `parent_phone`, `graduation_year_hebrew` (Hebrew year), `tags`, `notes`. File names point to a family-relation feature (`FamilyRelation`, `FamilyMembersDialog`, `SuggestFamilyDialog`) that links alumni who are relatives; after an alumnus is created, the add page opens a dialog that suggests family links.

Pages in the nav (`Layout.js`): `Alumni` (בוגרים), `AddAlumni` (הוסף בוגר), `Statistics` (סטטיסטיקות). Page URLs are built with `createPageUrl(pageName)`; `Layout` receives `children` and `currentPageName`.

## Conventions

- UI text is Hebrew; the root layout sets `dir="rtl"`. Keep new UI RTL and in Hebrew.
- Theme colors are CSS variables defined in `Layout.js` (`--primary`, `--primary-dark`, `--accent`, `--success`, `--warning`).
- After mutations, invalidate the matching react-query key (e.g. `['alumni']`).

## Token usage

Follow the rules in @TOKEN_SAVING.md.
