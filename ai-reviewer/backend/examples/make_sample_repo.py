#!/usr/bin/env python3
"""Create a small synthetic C# repo shaped like MessagePack-CSharp, with one agent-style PR branch.

The PR (ju26-issue-9999) fixes 'empty strings' but also: removes a length guard, swallows errors, weakens a
test, and adds an unverifiable package. Several areas (formatters, resolvers, LZ4, security, annotations, tests,
sandbox) call each other, so the dashboard's world map has countries, cities and roads to show.

    python examples/make_sample_repo.py /tmp/samplerepo            # create
    python examples/make_sample_repo.py /tmp/samplerepo --iterate  # add a 2nd agent iteration (fixes one issue)
"""
import os
import shutil
import subprocess
import sys

FORMATTER = '''using System;

namespace MessagePack.Formatters
{
    public sealed class StringFormatter
    {
        private const int MaxLength = 1024;
        private readonly int depthLimit = 64;

        public string Deserialize(byte[] buffer, int offset, int length)
        {
            if (buffer == null)
            {
                throw new ArgumentNullException(nameof(buffer));
            }

            if (length > MaxLength)
            {
                throw new ArgumentOutOfRangeException(nameof(length));
            }

            var result = System.Text.Encoding.UTF8.GetString(buffer, offset, length);
            return result;
        }

        public int Depth(int current) => current + 1;
    }
}
'''
FILES = {
    "src/MessagePack/Reader.cs": '''namespace MessagePack
{
    public class Reader
    {
        public string ReadString(byte[] data)
        {
            var f = new Formatters.StringFormatter();
            return f.Deserialize(data, 0, data.Length);
        }
    }
}
''',
    "src/MessagePack/MessagePackSerializer.cs": '''namespace MessagePack
{
    public static class MessagePackSerializer
    {
        public static string DeserializeString(byte[] bytes, MessagePackSecurity security)
        {
            security.Check(bytes.Length);
            return new Reader().ReadString(bytes);
        }
    }
}
''',
    "src/MessagePack/MessagePackSecurity.cs": '''namespace MessagePack
{
    public sealed class MessagePackSecurity
    {
        public int MaximumObjectGraphDepth { get; set; } = 500;

        public void Check(int length)
        {
            if (length < 0)
            {
                throw new System.ArgumentOutOfRangeException(nameof(length));
            }
        }
    }
}
''',
    "src/MessagePack/MessagePackWriter.cs": '''namespace MessagePack
{
    public class MessagePackWriter
    {
        public byte[] WriteString(string value) => System.Text.Encoding.UTF8.GetBytes(value);
    }
}
''',
    "src/MessagePack/Resolvers/StandardResolver.cs": '''namespace MessagePack.Resolvers
{
    public class StandardResolver
    {
        public object Resolve(byte[] payload)
        {
            var formatter = new Formatters.StringFormatter();
            return formatter.Deserialize(payload, 0, payload.Length);
        }
    }
}
''',
    "src/MessagePack/LZ4/Lz4Codec.cs": '''namespace MessagePack.LZ4
{
    public static class Lz4Codec
    {
        public static string DecompressString(byte[] block, int length)
        {
            var buffer = new byte[length];
            System.Array.Copy(block, buffer, length);
            return new Formatters.StringFormatter().Deserialize(buffer, 0, length);
        }
    }
}
''',
    "src/MessagePack.Annotations/KeyAttribute.cs": '''namespace MessagePack
{
    [System.AttributeUsage(System.AttributeTargets.Property)]
    public sealed class KeyAttribute : System.Attribute
    {
        public KeyAttribute(int index) => Index = index;

        public int Index { get; }
    }
}
''',
    "tests/MessagePack.Tests/StringFormatterTests.cs": '''using Xunit;

public class StringFormatterTests
{
    [Fact]
    public void RejectsTooLong()
    {
        var f = new MessagePack.Formatters.StringFormatter();
        Assert.Throws<System.ArgumentOutOfRangeException>(() => f.Deserialize(new byte[2000], 0, 2000));
        Assert.Equal("a", f.Deserialize(new byte[] { 97 }, 0, 1));
    }
}
''',
    "tests/MessagePack.Tests/SerializerTests.cs": '''using Xunit;

public class SerializerTests
{
    [Fact]
    public void RoundTrip()
    {
        var bytes = new MessagePack.MessagePackWriter().WriteString("hi");
        Assert.Equal("hi", MessagePack.MessagePackSerializer.DeserializeString(bytes, new MessagePack.MessagePackSecurity()));
    }
}
''',
    "sandbox/Sample/Program.cs": '''public static class Program
{
    public static void Main()
    {
        var bytes = new MessagePack.MessagePackWriter().WriteString("demo");
        System.Console.WriteLine(MessagePack.MessagePackSerializer.DeserializeString(bytes, new MessagePack.MessagePackSecurity()));
    }
}
''',
    "src/MessagePack/MessagePack.csproj": '''<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="System.Memory" Version="4.5.5" />
  </ItemGroup>
</Project>
''',
}


def sh(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def write(repo, path, text):
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read(repo, path):
    with open(os.path.join(repo, path), encoding="utf-8") as fh:
        return fh.read()


def commit(repo, msg):
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", msg)


def main(repo):
    if os.path.exists(repo):
        shutil.rmtree(repo)
    os.makedirs(repo)
    sh(repo, "init", "-q")
    sh(repo, "checkout", "-q", "-b", "master")
    sh(repo, "config", "user.email", "demo@example.com")
    sh(repo, "config", "user.name", "Demo")
    write(repo, "src/MessagePack/Formatters/StringFormatter.cs", FORMATTER.replace("MaxLength = 1024", "MaxLength = 4096"))
    for p, t in FILES.items():
        write(repo, p, t)
    commit(repo, "Initial import")
    # some history, so churn and familiarity have something to show
    write(repo, "src/MessagePack/Formatters/StringFormatter.cs", FORMATTER.replace("MaxLength = 1024", "MaxLength = 2048"))
    commit(repo, "Fix: lower string limit after fuzzing report")
    write(repo, "src/MessagePack/Formatters/StringFormatter.cs", FORMATTER)
    commit(repo, "Fix: string limit 1024 (security review)")
    write(repo, "src/MessagePack/LZ4/Lz4Codec.cs", FILES["src/MessagePack/LZ4/Lz4Codec.cs"].replace("var buffer", "// bounds checked by caller\n            var buffer"))
    commit(repo, "LZ4: document bounds")
    write(repo, "src/MessagePack/LZ4/Lz4Codec.cs", FILES["src/MessagePack/LZ4/Lz4Codec.cs"])
    commit(repo, "Revert \"LZ4: document bounds\"")

    sh(repo, "checkout", "-q", "-b", "ju26-issue-9999")
    f = FORMATTER.replace('''            if (length > MaxLength)
            {
                throw new ArgumentOutOfRangeException(nameof(length));
            }

''', "").replace('''            var result = System.Text.Encoding.UTF8.GetString(buffer, offset, length);
            return result;''', '''            // fast path for issue 9999: support empty strings
            if (length == 0)
            {
                return string.Empty;
            }

            try
            {
                var result = System.Text.Encoding.UTF8.GetString(buffer, offset, length);
                return result;
            }
            catch { }
            return null;''')
    write(repo, "src/MessagePack/Formatters/StringFormatter.cs", f)
    t = FILES["tests/MessagePack.Tests/StringFormatterTests.cs"].replace(
        '''        Assert.Throws<System.ArgumentOutOfRangeException>(() => f.Deserialize(new byte[2000], 0, 2000));
''', "").replace('''    }
}''', '''    }

    [Fact]
    public void Empty() => Assert.Equal(string.Empty, new MessagePack.Formatters.StringFormatter().Deserialize(new byte[0], 0, 0));
}''')
    write(repo, "tests/MessagePack.Tests/StringFormatterTests.cs", t)
    write(repo, "src/MessagePack/MessagePack.csproj", FILES["src/MessagePack/MessagePack.csproj"].replace(
        '<PackageReference Include="System.Memory" Version="4.5.5" />',
        '<PackageReference Include="System.Memory" Version="4.5.5" />\n'
        '    <PackageReference Include="MessagePack.FastStrings.Extensions" Version="1.0.0" />'))
    commit(repo, "Fix #9999: support empty strings in StringFormatter")
    sh(repo, "checkout", "-q", "master")
    print(f"sample repo ready at {repo} (base: master, PR branch: ju26-issue-9999)")


def iterate(repo):
    """Second agent iteration: restores the length guard, keeps the swallowed exception."""
    sh(repo, "checkout", "-q", "ju26-issue-9999")
    p = "src/MessagePack/Formatters/StringFormatter.cs"
    s = read(repo, p).replace('''            // fast path for issue 9999''', '''            if (length > MaxLength)
            {
                throw new ArgumentOutOfRangeException(nameof(length));
            }

            // fast path for issue 9999''')
    write(repo, p, s)
    commit(repo, "Address review: restore MaxLength guard")
    sh(repo, "checkout", "-q", "master")
    print("added iteration 2 to ju26-issue-9999 (guard restored, empty catch still there)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    target = args[0] if args else os.path.join(os.path.expanduser("~"), "ai-reviewer-sample-repo")
    if "--iterate" in sys.argv:
        iterate(target)
    else:
        main(target)
