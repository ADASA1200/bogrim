// בונה את manifest.xml ואת shortcuts.json מתוך scripts/ribbon.mjs.
// שימוש: node scripts/build-manifest.mjs [כתובת-בסיס]   (ברירת מחדל https://localhost:3000)
import { writeFileSync } from 'node:fs';
import { COMMANDS, TOOLS, VOWELS, SIGNS, TAAMIM_ITEMS } from './ribbon.mjs';

const BASE = (process.argv[2] || 'https://localhost:3000').replace(/\/$/, '');
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');

const images = [];
const shortStrings = [];
const longStrings = [];

function res(id, label, tip) {
  shortStrings.push(`<bt:String id="${id}.Label" DefaultValue="${esc(label)}"/>`);
  longStrings.push(`<bt:String id="${id}.Tip" DefaultValue="${esc(tip)}"/>`);
  for (const s of [16, 32, 80]) images.push(`<bt:Image id="${id}.${s}" DefaultValue="${BASE}/assets/ribbon/${id}-${s}.png"/>`);
}

const icon = (id) => `<Icon><bt:Image size="16" resid="${id}.16"/><bt:Image size="32" resid="${id}.32"/><bt:Image size="80" resid="${id}.80"/></Icon>`;
const action = (id) => `<Action xsi:type="ExecuteFunction"><FunctionName>${id}</FunctionName></Action>`;

function button(c) {
  res(c.id, c.label, c.tip);
  return `<Control xsi:type="Button" id="NK.${c.id}"><Label resid="${c.id}.Label"/><Supertip><Title resid="${c.id}.Label"/><Description resid="${c.id}.Tip"/></Supertip>${icon(c.id)}${action(c.id)}</Control>`;
}

function menu(id, label, tip, iconId, items) {
  res(id, label, tip);
  for (const s of [16, 32, 80]) images.push(`<bt:Image id="${id}.${s}" DefaultValue="${BASE}/assets/ribbon/${iconId}-${s}.png"/>`);
  images.splice(images.length - 6, 3); // את הסמלים של התפריט לוקחים מהפריט הראשון
  const its = items.map((c) => {
    res(c.id, c.label, c.tip);
    return `<Item id="NK.${c.id}"><Label resid="${c.id}.Label"/><Supertip><Title resid="${c.id}.Label"/><Description resid="${c.id}.Tip"/></Supertip>${icon(c.id)}${action(c.id)}</Item>`;
  });
  return `<Control xsi:type="Menu" id="NK.${id}"><Label resid="${id}.Label"/><Supertip><Title resid="${id}.Label"/><Description resid="${id}.Tip"/></Supertip>${icon(id)}<Items>${its.join('')}</Items></Control>`;
}

function group(id, label, controls) {
  shortStrings.push(`<bt:String id="${id}.Label" DefaultValue="${esc(label)}"/>`);
  return `<Group id="NK.${id}"><Label resid="${id}.Label"/>${icon(controls.iconId)}${controls.xml.join('')}</Group>`;
}

const groups = [
  group('G.Nikud', 'ניקוד', { iconId: 'autoNikud', xml: COMMANDS.map(button) }),
  group('G.Tools', 'כלים', { iconId: 'openSettings', xml: TOOLS.map(button) }),
  group('G.Vowels', 'כפתורי ניקוד', { iconId: VOWELS[0].id, xml: [...VOWELS, ...SIGNS].map(button) }),
  group('G.Taamim', 'טעמי המקרא', {
    iconId: TAAMIM_ITEMS[0].id,
    xml: [menu('M.Taamim', 'טעמים', 'הוספת טעם אחרי האות שלפני הסמן.', TAAMIM_ITEMS[0].id, TAAMIM_ITEMS)],
  }),
];
shortStrings.push('<bt:String id="Tab.Label" DefaultValue="ניקוד קל"/>');
shortStrings.push('<bt:String id="GetStarted.Title" DefaultValue="ניקוד קל מוכן לעבודה"/>');
longStrings.push('<bt:String id="GetStarted.Description" DefaultValue="הכפתורים נמצאים בלשונית &quot;ניקוד קל&quot;."/>');

const xml = `<?xml version="1.0" encoding="UTF-8"?>
<!-- נוצר על ידי scripts/build-manifest.mjs. לא לערוך ידנית. -->
<OfficeApp xmlns="http://schemas.microsoft.com/office/appforoffice/1.1"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xmlns:bt="http://schemas.microsoft.com/office/officeappbasictypes/1.0"
           xmlns:ov="http://schemas.microsoft.com/office/taskpaneappversionoverrides"
           xsi:type="TaskPaneApp">
  <Id>f585020a-505d-455a-a72b-7872291e5611</Id>
  <Version>1.1.0.0</Version>
  <ProviderName>Nikud Kal</ProviderName>
  <DefaultLocale>he-IL</DefaultLocale>
  <DisplayName DefaultValue="ניקוד קל"/>
  <Description DefaultValue="ניקוד מסמכי Word לפי מילון שאתם בונים, ניקוד פסוקים לפי התנ&quot;ך, וכפתורי ניקוד וטעמים."/>
  <IconUrl DefaultValue="${BASE}/assets/icon-32.png"/>
  <HighResolutionIconUrl DefaultValue="${BASE}/assets/icon-64.png"/>
  <SupportUrl DefaultValue="${BASE}/README.md"/>
  <AppDomains>
    <AppDomain>${BASE}</AppDomain>
  </AppDomains>
  <Hosts>
    <Host Name="Document"/>
  </Hosts>
  <Requirements>
    <Sets DefaultMinVersion="1.3">
      <Set Name="WordApi" MinVersion="1.3"/>
    </Sets>
  </Requirements>
  <DefaultSettings>
    <SourceLocation DefaultValue="${BASE}/src/taskpane.html"/>
  </DefaultSettings>
  <Permissions>ReadWriteDocument</Permissions>
  <VersionOverrides xmlns="http://schemas.microsoft.com/office/taskpaneappversionoverrides" xsi:type="VersionOverridesV1_0">
    <Requirements>
      <bt:Sets DefaultMinVersion="1.1">
        <bt:Set Name="SharedRuntime" MinVersion="1.1"/>
      </bt:Sets>
    </Requirements>
    <Hosts>
      <Host xsi:type="Document">
        <Runtimes>
          <Runtime resid="Taskpane.Url" lifetime="long"/>
        </Runtimes>
        <DesktopFormFactor>
          <GetStarted>
            <Title resid="GetStarted.Title"/>
            <Description resid="GetStarted.Description"/>
            <LearnMoreUrl resid="Readme.Url"/>
          </GetStarted>
          <FunctionFile resid="Taskpane.Url"/>
          <ExtensionPoint xsi:type="PrimaryCommandSurface">
            <CustomTab id="NK.Tab">
              ${groups.join('\n              ')}
              <Label resid="Tab.Label"/>
            </CustomTab>
          </ExtensionPoint>
        </DesktopFormFactor>
      </Host>
    </Hosts>
    <Resources>
      <bt:Images>
        ${images.join('\n        ')}
      </bt:Images>
      <bt:Urls>
        <bt:Url id="Taskpane.Url" DefaultValue="${BASE}/src/taskpane.html"/>
        <bt:Url id="Readme.Url" DefaultValue="${BASE}/README.md"/>
      </bt:Urls>
      <bt:ShortStrings>
        ${shortStrings.join('\n        ')}
      </bt:ShortStrings>
      <bt:LongStrings>
        ${longStrings.join('\n        ')}
      </bt:LongStrings>
    </Resources>
  </VersionOverrides>
  <ExtendedOverrides Url="${BASE}/shortcuts.json"/>
</OfficeApp>
`;
writeFileSync(new URL('../manifest.xml', import.meta.url), xml);

const shortcuts = {
  actions: [...COMMANDS, ...TOOLS].map((c) => ({ id: c.id, type: 'ExecuteFunction', name: c.label })),
  shortcuts: [...COMMANDS, ...TOOLS].filter((c) => c.key).map((c) => ({ action: c.id, key: { default: c.key } })),
};
writeFileSync(new URL('../shortcuts.json', import.meta.url), JSON.stringify(shortcuts, null, 2) + '\n');
console.log(`manifest.xml: ${groups.length} groups, ${images.length / 3} icons; shortcuts.json: ${shortcuts.shortcuts.length} keys`);
