# GitHubRepoStatus Component - Visual Guide

## Component Appearance

### State 1: Creating (Loading)
```
┌─────────────────────────────────────────────────────────┐
│  ⟳ Creating repository...                               │
│    Setting up your GitHub repository                    │
└─────────────────────────────────────────────────────────┘
   Blue theme (bg-blue-500/10, border-blue-500/20)
   - Animated spinner icon (rotating)
   - Primary message in blue
   - Helper text in gray
```

### State 2: Failed (Error)
```
┌─────────────────────────────────────────────────────────┐
│  ✕ Repository creation failed                           │
│    Failed to create repository. Retrying               │
│    automatically...                                     │
└─────────────────────────────────────────────────────────┘
   Red theme (bg-red-500/10, border-red-500/20)
   - X circle icon (red)
   - Error message in red
   - Retry message in gray
```

### State 3: Created (Success)
```
┌─────────────────────────────────────────────────────────┐
│  ✓ Repository created successfully                      │
│    Your GitHub repository is ready                      │
│                                                          │
│        example-project ↗                                │
│        (clickable link in blue)                         │
│                                                          │
│        ✓ Initial commit   🌿 Main branch   🛡️ Protection │
│        enabled                                           │
│                                                          │
│        ┌──────────────────┐                             │
│        │ View on GitHub ↗ │                             │
│        └──────────────────┘                             │
└─────────────────────────────────────────────────────────┘
   Green theme (bg-green-500/10, border-green-500/20)
   - Checkmark icon (green)
   - Success message in green
   - Repository URL (clickable, opens new tab)
   - 3 metadata icons with labels
   - Outlined button (hover effects)
```

## Color Palette

### Creating State
- Background: `bg-blue-500/10` (10% opacity blue)
- Border: `border-blue-500/20` (20% opacity blue)
- Icon: `text-blue-400` (bright blue)
- Primary text: `text-blue-300` (medium blue)
- Helper text: `text-gray-400` (gray)

### Failed State
- Background: `bg-red-500/10` (10% opacity red)
- Border: `border-red-500/20` (20% opacity red)
- Icon: `text-red-400` (bright red)
- Primary text: `text-red-300` (medium red)
- Helper text: `text-gray-400` (gray)

### Created State
- Background: `bg-green-500/10` (10% opacity green)
- Border: `border-green-500/20` (20% opacity green)
- Icon: `text-green-400` (bright green)
- Primary text: `text-green-300` (medium green)
- URL link: `text-blue-400 hover:text-blue-300` (blue)
- Metadata icons:
  - Initial commit: `text-green-400` (green checkmark)
  - Main branch: `text-blue-400` (blue branch icon)
  - Protection: `text-purple-400` (purple shield)
- Button: Green-themed outline with hover effects

## Layout Structure

### Creating & Failed States (Horizontal Layout)
```
[Icon] [Text Content]
  ↓         ↓
  5x5    Primary message
         Helper message
```

### Created State (Vertical Layout)
```
[Icon] [Success Header]
       ↓
     [Repository URL]
       ↓
     [Metadata Icons Row]
       ↓
     [View on GitHub Button]
```

## Spacing & Sizing

### Overall Container
- Padding: `p-4` (1rem / 16px all sides)
- Border radius: `rounded-lg` (0.5rem / 8px)
- Border width: `border` (1px)

### Icon Sizes
- Main status icons: `w-5 h-5` (20px)
- Link icons: `w-3.5 h-3.5` (14px)
- Button icon: `w-3 h-3` (12px)
- Metadata icons: `w-3.5 h-3.5` (14px)

### Text Sizes
- Primary message: `text-sm font-medium` (14px, 500 weight)
- Helper text: `text-xs` (12px)
- URL link: `text-sm font-mono` (14px, monospace)
- Metadata labels: `text-xs` (12px)
- Button text: `text-xs` (12px)

### Gaps & Spacing
- Main icon to content: `gap-3` (0.75rem / 12px)
- URL icon gap: `gap-1.5` (0.375rem / 6px)
- Metadata icons gap: `gap-4` (1rem / 16px)
- Vertical spacing: `space-y-3` (0.75rem / 12px)

## Responsive Behavior

### Mobile (< 640px)
- Metadata icons wrap to multiple rows (`flex-wrap`)
- Long URLs break to prevent overflow (`break-all`)
- Button remains visible below content
- All spacing maintains readability

### Tablet (640px - 1024px)
- Metadata icons typically fit in one row
- Optimal layout maintained

### Desktop (> 1024px)
- Full layout with all elements in optimal positions
- Hover effects more prominent

## Interactive Elements

### Repository URL Link
```
Default:  text-blue-400
Hover:    text-blue-300 + underline
Active:   Opens in new tab
```

### "View on GitHub" Button
```
Default:  border-green-500/30
Hover:    bg-green-500/10 + border-green-500/50
Active:   Opens in new tab
Focus:    Ring outline (accessibility)
```

## Animation Details

### Loader Spinner (Creating State)
- Class: `animate-spin`
- Duration: ~1 second per rotation
- Continuous until state changes
- GPU accelerated (CSS transform)

### Hover Transitions
- Duration: Default Tailwind transition (~200ms)
- Properties: colors, background, border
- Easing: Default (ease-in-out)

## Accessibility Features

### Semantic Structure
```html
<div role="status">           <!-- Creating state -->
<div role="alert">            <!-- Failed state -->
<div>                         <!-- Created state -->
  <a href="..." target="_blank" rel="noopener noreferrer">
  <button>...</button>
</div>
```

### Keyboard Navigation
1. Tab to repository URL link
2. Tab to "View on GitHub" button
3. Enter/Space to activate
4. All interactive elements focusable

### Screen Reader Support
- Status messages are announced
- Link text is descriptive ("View on GitHub")
- Icon labels provided via text content
- Loading state is clearly indicated

## Usage Examples

### Example 1: Basic Integration
```tsx
<GitHubRepoStatus status="creating" />
```

### Example 2: With Repository URL
```tsx
<GitHubRepoStatus
  status="created"
  repoUrl="https://github.com/ainative/my-project"
/>
```

### Example 3: Error State
```tsx
<GitHubRepoStatus status="failed" />
```

### Example 4: Dynamic State
```tsx
const [status, setStatus] = useState<'creating' | 'created' | 'failed'>('creating');

<GitHubRepoStatus
  status={status}
  repoUrl={status === 'created' ? repoUrl : undefined}
/>
```

## Dark Theme Compatibility

The component is designed for dark backgrounds:
- All colors have sufficient contrast on dark surfaces
- Background overlays use low opacity for subtle effect
- Border colors provide clear visual separation
- Text colors are optimized for dark mode readability

### Recommended Background
- Minimum: `bg-gray-900` or darker
- Optimal: `bg-[#0D1117]` (GitHub dark theme)
- Pattern: Works on any dark background (#000 to #1F1F1F)

## Component Hierarchy

```
GitHubRepoStatus
├── Creating State
│   ├── Loader2 Icon (animated)
│   └── Text Content
│       ├── Primary Message
│       └── Helper Text
├── Failed State
│   ├── XCircle Icon
│   └── Text Content
│       ├── Error Message
│       └── Retry Message
└── Created State
    ├── Header Section
    │   ├── CheckCircle Icon
    │   └── Success Message
    ├── URL Section
    │   └── Repository Link (with ExternalLink icon)
    ├── Metadata Section
    │   ├── Initial Commit (CheckCircle + label)
    │   ├── Main Branch (GitBranch + label)
    │   └── Protection (Shield + label)
    └── Action Section
        └── View on GitHub Button (with ExternalLink icon)
```

## Visual Design Principles

1. **Clear Status Indication**: Color-coded states (blue/red/green)
2. **Progressive Disclosure**: More info shown on success
3. **Action Oriented**: Clear CTA in success state
4. **Feedback Rich**: Multiple indicators (icon, text, color)
5. **Scannable**: Good visual hierarchy with icons and spacing
6. **Trustworthy**: Security indicators (shield, protection)
7. **Clickable**: Clear affordances for interactive elements

## Comparison with Similar Components

### vs AgentSwarmTerminal
- **Similar**: Status-based rendering, color coding, icons
- **Different**: More compact, focused on single event vs. stream

### vs Standard Status Badge
- **Similar**: Color-coded states
- **Different**: Richer information, interactive elements, metadata

## Print/Screenshot Friendly

- High contrast ensures visibility in screenshots
- Clear visual hierarchy maintains meaning without interaction
- Icon + text redundancy ensures clarity
- Suitable for documentation and support materials

---

**Visual Design Version**: 1.0
**Last Updated**: 2025-12-05
**Component File**: `/Users/aideveloper/core/AINative-website/src/components/GitHubRepoStatus.tsx`
