import { SignInButton } from './sign-in-button';

export default function SignInPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-8">
      <div className="space-y-2 text-center">
        <h1 className="text-2xl font-semibold">Sign in to MeetingOS</h1>
        <p className="text-sm text-slate-600">
          Continue with your Google account to access your meetings.
        </p>
      </div>
      <SignInButton />
    </main>
  );
}
