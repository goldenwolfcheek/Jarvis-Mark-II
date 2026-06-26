const path = require('path');
const fs = require('fs');

async function main() {
  const { downloadArtifact } = await import('@electron/get');
  const extract = require('extract-zip');

  const electronDir = path.join(process.cwd(), 'node_modules/electron');
  const { version } = require(path.join(electronDir, 'package.json'));

  console.log(`Downloading Electron v${version} for win32-x64...`);

  const zipPath = await downloadArtifact({
    version,
    artifactName: 'electron',
    force: true,
    platform: 'win32',
    arch: 'x64',
  });

  console.log(`Downloaded to: ${zipPath}`);

  const distPath = path.join(electronDir, 'dist');
  await extract(zipPath, { dir: distPath });
  console.log('Extracted successfully');

  // Write path.txt
  fs.writeFileSync(path.join(electronDir, 'path.txt'), 'electron.exe');
  console.log('path.txt written');

  // Verify
  if (fs.existsSync(path.join(distPath, 'electron.exe'))) {
    console.log('✅ electron.exe installed successfully');
  } else {
    console.log('❌ electron.exe not found after extraction');
  }
}

main().catch(e => {
  console.error('Failed:', e.message);
  console.error(e.stack);
  process.exit(1);
});
